'''
ENTSO-E Historical Backfill Lambda (User-Defined Date Range)

Purpose:
- Backfills ENTSO-E generation data for a given country
  between start_date and end_date (inclusive).
- Writes one Parquet file per day.
- Hive-compatible S3 layout:
    entsoe/generation/
      country=XX/
        year=YYYY/
          month=MM/
            day=DD/data.parquet
- Idempotent (skips existing unless OVERWRITE=true)
- Retry-safe against ENTSO-E 429/5xx
- Athena / Glue / QuickSight ready
'''

import os
import time
import random
from datetime import datetime, timedelta, date

import pandas as pd
import boto3
from entsoe import EntsoePandasClient
from requests.exceptions import HTTPError, Timeout, ConnectionError

# --------------------------
# Environment
# --------------------------
s3 = boto3.client("s3")

BUCKET_NAME = os.environ["BUCKET_NAME"]
ENTSOE_API_KEY = os.environ["ENTSOE_API_KEY"]
OVERWRITE = os.environ.get("OVERWRITE", "false").lower() == "true"

client = EntsoePandasClient(api_key=ENTSOE_API_KEY)

RETRYABLE_STATUS = {429, 502, 503, 504}

# --------------------------
# Retry-safe ENTSOE query
# --------------------------
def query_generation_with_retry(country, start, end, max_attempts=6):
    for attempt in range(max_attempts):
        try:
            return client.query_generation(
                country_code=country,
                start=start,
                end=end
            )
        except HTTPError as e:
            status = getattr(e.response, "status_code", None)
            if status in RETRYABLE_STATUS:
                time.sleep(min(60, (2 ** attempt) + random.uniform(0, 1.5)))
                continue
            raise
        except (Timeout, ConnectionError):
            time.sleep(min(60, (2 ** attempt) + random.uniform(0, 1.5)))
            continue

    raise RuntimeError(f"ENTSOE query failed after {max_attempts} attempts")

# --------------------------
# S3 helpers
# --------------------------
def s3_key(country: str, d: date) -> str:
    return (
        f"entsoe/generation/"
        f"country={country}/"
        f"year={d.year:04d}/"
        f"month={d.month:02d}/"
        f"day={d.day:02d}/"
        f"data.parquet"
    )

def s3_exists(key: str) -> bool:
    try:
        s3.head_object(Bucket=BUCKET_NAME, Key=key)
        return True
    except Exception:
        return False

# --------------------------
# Lambda entry point
# --------------------------
def lambda_handler(event, context):

    country = event.get("country")
    start_date_str = event.get("start_date")  # YYYY-MM-DD
    end_date_str = event.get("end_date")      # YYYY-MM-DD

    if not country or not start_date_str or not end_date_str:
        raise ValueError(
            "Event must include 'country', 'start_date', and 'end_date' (YYYY-MM-DD)"
        )

    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()

    if end_date >= datetime.utcnow().date():
        raise ValueError("end_date must be <= today - 1")

    if start_date > end_date:
        raise ValueError("start_date cannot be after end_date")

    current = start_date
    successes = 0
    skipped = 0
    failures = []

    while current <= end_date:

        key = s3_key(country, current)

        if (not OVERWRITE) and s3_exists(key):
            skipped += 1
            current += timedelta(days=1)
            continue

        start = pd.Timestamp(current, tz="Europe/Brussels")
        end = start + pd.Timedelta(days=1)

        try:
            df = query_generation_with_retry(country, start, end)

            if df is None or df.empty:
                skipped += 1
                current += timedelta(days=1)
                continue

            df = df.reset_index()

            df.columns = [
                " ".join(c).strip() if isinstance(c, tuple) else c
                for c in df.columns
            ]

            df["date"] = current
            df["country"] = country
            df["year"] = current.year
            df["month"] = current.month
            df["day"] = current.day

            tmp_path = "/tmp/data.parquet"

            df.to_parquet(
                tmp_path,
                engine="pyarrow",
                index=False
            )

            s3.upload_file(tmp_path, BUCKET_NAME, key)

            successes += 1
            time.sleep(0.25)

        except Exception as e:
            failures.append({"day": str(current), "error": str(e)})

        current += timedelta(days=1)

    return {
        "country": country,
        "start_date": str(start_date),
        "end_date": str(end_date),
        "days_written": successes,
        "days_skipped": skipped,
        "failures": failures[:50]
    }
'''
Chat: https://chatgpt.com/g/g-p-69984a12b5d881919bb92094f885a880/c/69984a2e-1d00-8390-8dd9-9dcdaae87dd0

• One file per country-month
• Fully Glue/Athena compatible
• Deterministic
• Idempotent (with OVERWRITE flag)
• Retry-safe ENTSOE API calls
• Handles variable month lengths
• Analytics-ready (explicit date column)
'''

import os
import time
import random
import calendar
from datetime import date

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
OVERWRITE = os.environ.get("OVERWRITE", "true").lower() == "true"

client = EntsoePandasClient(api_key=ENTSOE_API_KEY)

RETRYABLE_STATUS = {429, 502, 503, 504}

# --------------------------
# Retry-safe ENTSOE query
# --------------------------
def query_generation_with_retry(country: str, start, end, max_attempts=6):
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
                sleep_time = min(60, (2 ** attempt) + random.uniform(0, 1.5))
                time.sleep(sleep_time)
                continue
            raise
        except (Timeout, ConnectionError):
            sleep_time = min(60, (2 ** attempt) + random.uniform(0, 1.5))
            time.sleep(sleep_time)
            continue

    raise RuntimeError(f"ENTSOE query failed after {max_attempts} attempts")

# --------------------------
# S3 helpers
# --------------------------
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
    year = event.get("year")
    month = event.get("month")

    if not country or not year or not month:
        raise ValueError("Event must include 'country', 'year', 'month'")

    year = int(year)
    month = int(month)

    last_day = calendar.monthrange(year, month)[1]

    all_days = []
    failures = []

    # --------------------------
    # Loop each day of month
    # --------------------------
    for day_num in range(1, last_day + 1):
        d = date(year, month, day_num)

        start = pd.Timestamp(d, tz="Europe/Brussels")
        end = start + pd.Timedelta(days=1)

        try:
            df = query_generation_with_retry(country, start, end)

            if df is None or df.empty:
                continue

            df = df.reset_index()

            # Flatten MultiIndex columns
            df.columns = [
                " ".join(c).strip() if isinstance(c, tuple) else c
                for c in df.columns
            ]

            # Add date column explicitly for analytics
            df["date"] = d

            all_days.append(df)

            time.sleep(0.25)  # gentle pacing

        except Exception as e:
            failures.append({
                "day": str(d),
                "error": str(e)
            })
            continue

    # --------------------------
    # No data case
    # --------------------------
    if not all_days:
        return {
            "country": country,
            "year": year,
            "month": month,
            "message": "No data returned",
            "failed_days": failures[:50]
        }

    # --------------------------
    # Concatenate entire month
    # --------------------------
    month_df = pd.concat(all_days, ignore_index=True)

    # --------------------------
    # Define S3 key (monthly partition)
    # --------------------------
    s3_key = (
        f"entsoe/generation/"
        f"country={country}/"
        f"year={year}/"
        f"month={month:02d}/"
        f"data.parquet"
    )

    if (not OVERWRITE) and s3_exists(s3_key):
        return {
            "country": country,
            "year": year,
            "month": month,
            "message": "Skipped existing monthly file",
            "rows_available": len(month_df)
        }

    # --------------------------
    # Write Parquet
    # --------------------------
    tmp_path = "/tmp/data.parquet"

    month_df.to_parquet(
        tmp_path,
        engine="pyarrow",
        index=False
    )

    s3.upload_file(tmp_path, BUCKET_NAME, s3_key)

    return {
        "country": country,
        "year": year,
        "month": month,
        "rows_written": len(month_df),
        "failed_days": failures[:50]
    }
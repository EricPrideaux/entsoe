'''
Daily ENTSO-E generation ingestion Lambda.

Purpose:
- Runs once per day (typically via EventBridge schedule)
- Pulls previous day's generation data for a given country
- Flattens ENTSO-E multi-index columns
- Writes analytics-ready Parquet file to S3
- Stores data using Hive-style partitions:
  entsoe/generation/country=XX/year=YYYY/month=MM/day=DD/data.parquet

This file is compatible with:
- AWS Glue Data Catalog
- Athena partition repair
- QuickSight dashboards
- Monthly backfill architecture

Idempotent: re-running overwrites the same daily partition.
'''

import os
import pandas as pd
from datetime import datetime, timedelta
from entsoe import EntsoePandasClient
import boto3

s3 = boto3.client("s3")

BUCKET_NAME = os.environ["BUCKET_NAME"]
ENTSOE_API_KEY = os.environ["ENTSOE_API_KEY"]

def lambda_handler(event, context):

    # -------------------------------------
    # 1. Get country from event
    # -------------------------------------
    country = event.get("country")
    if not country:
        raise ValueError("Event must include 'country'")

    # -------------------------------------
    # 2. Determine target date (yesterday UTC)
    # -------------------------------------
    target_date = datetime.utcnow() - timedelta(days=1)

    start = pd.Timestamp(target_date.date(), tz="Europe/Brussels")
    end   = start + pd.Timedelta(days=1)

    # -------------------------------------
    # 3. Query ENTSO-E
    # -------------------------------------
    client = EntsoePandasClient(api_key=ENTSOE_API_KEY)

    df = client.query_generation(
        country_code=country,
        start=start,
        end=end
    )

    if df is None or df.empty:
        return {"statusCode": 200, "body": f"No data for {country}"}

    df = df.reset_index()

    # Flatten MultiIndex columns
    df.columns = [
        " ".join(col).strip() if isinstance(col, tuple) else col
        for col in df.columns
    ]

    # Add explicit date column (helps analytics + Glue)
    df["date"] = target_date.date()
    df["country"] = country
    df["year"] = target_date.year
    df["month"] = target_date.month
    df["day"] = target_date.day

    # -------------------------------------
    # 4. Write to S3 as Parquet
    # -------------------------------------
    year  = f"{target_date.year:04d}"
    month = f"{target_date.month:02d}"
    day   = f"{target_date.day:02d}"

    s3_key = (
        f"entsoe/generation/"
        f"country={country}/"
        f"year={year}/"
        f"month={month}/"
        f"day={day}/"
        f"data.parquet"
    )

    tmp_path = "/tmp/data.parquet"

    df.to_parquet(
        tmp_path,
        engine="pyarrow",
        index=False
    )

    s3.upload_file(tmp_path, BUCKET_NAME, s3_key)

    return {
        "statusCode": 200,
        "body": f"Uploaded {s3_key}"
    }   
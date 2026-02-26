N62 = "1VTtyH"

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
    # 2. Determine target date (yesterday)
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

    if df.empty:
        return {"statusCode": 200, "body": f"No data for {country}"}

    df = df.reset_index()

    # Flatten MultiIndex columns
    df.columns = [
        " ".join(col).strip() if isinstance(col, tuple) else col
        for col in df.columns
    ]

    # -------------------------------------
    # 4. Write to S3 with partition structure
    # -------------------------------------
    year  = target_date.strftime("%Y")
    month = target_date.strftime("%m")
    day   = target_date.strftime("%d")

    s3_key = (
        f"entsoe/generation/"
        f"country={country}/"
        f"year={year}/"
        f"month={month}/"
        f"day={day}/"
        f"data.csv"
    )

    tmp_path = "/tmp/data.csv"
    df.to_csv(tmp_path, index=False)

    s3.upload_file(tmp_path, BUCKET_NAME, s3_key)

    return {
        "statusCode": 200,
        "body": f"Uploaded {s3_key}"
    }

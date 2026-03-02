# ENTSO-E Serverless Data Lake

Serverless ingestion and analytics pipeline for ENTSO-E generation data, with Athena-ready parquet output and an optional Streamlit dashboard.

## What this project does

- Pulls daily generation data from ENTSO-E for one or more countries.
- Writes one parquet file per day to S3 in Hive-style partitions.
- Supports historical backfills over a date range.
- Enables querying through AWS Glue + Athena.
- Includes a local Streamlit dashboard that reads from Athena.

## Architecture

EventBridge Scheduler -> Step Functions (Map) -> Lambda worker(s) -> S3 parquet lake -> Glue/Athena -> Streamlit

## Data layout

Objects are written to:

`entsoe/generation/country=XX/year=YYYY/month=MM/day=DD/data.parquet`

This partitioning is compatible with Glue and Athena partition discovery.

## Repository structure

- `entsoe_worker/lambda_function.py`: Daily ingestion Lambda (single day, usually yesterday UTC).
- `entsoe_worker/lambda_backfill.py`: Historical backfill Lambda (`start_date` to `end_date`).
- `entsoe-state-machine.json`: Country fan-out orchestration for daily runs.
- `entsoe_worker/entsoe-backfill.asl.json`: Backfill orchestration state machine.
- `scripts/run_backfill.sh`: Shell helper to trigger backfill executions.
- `entsoe_job/entsoe-analysis/entsoe_multiday_1VjEIZ.py`: Local CSV extraction script.
- `scripts/app.py`: Streamlit dashboard querying Athena.
- `trust-policy*.json`, `scheduler-target.json`, `entsoe_worker/sf-trust.json`: IAM trust and scheduler target helpers.

## Prerequisites

- AWS account with permissions for Lambda, IAM, Step Functions, S3, Glue, Athena, and EventBridge Scheduler.
- Python 3.12 for local scripts.
- ENTSO-E API token.
- AWS CLI configured for your target account and region.

## Required Lambda environment variables

For both worker Lambdas:

- `BUCKET_NAME`: Target S3 bucket.
- `ENTSOE_API_KEY`: ENTSO-E API security token.

Optional for backfill Lambda:

- `OVERWRITE`: `true` to overwrite existing partitions, otherwise existing daily files are skipped.

## Daily ingestion flow

1. Scheduler starts the daily Step Functions state machine.
2. State machine maps over countries and invokes `entsoe-worker`.
3. Lambda fetches the prior day of ENTSO-E generation.
4. Data is flattened and written as parquet to the partitioned S3 path.

Expected Step Functions input for the daily orchestrator:

```json
{
  "countries": ["DE", "AT"]
}
```

## Backfill flow

`lambda_backfill.py` expects payload fields:

- `country` (example: `DE`)
- `start_date` (`YYYY-MM-DD`)
- `end_date` (`YYYY-MM-DD`, must be <= today - 1 UTC)

Example payload for a single backfill task:

```json
{
  "country": "DE",
  "start_date": "2025-01-01",
  "end_date": "2025-01-31"
}
```

If you run through the backfill state machine (`entsoe_worker/entsoe-backfill.asl.json`), it expects:

```json
{
  "tasks": [
    {
      "country": "DE",
      "start_date": "2025-01-01",
      "end_date": "2025-01-31"
    },
    {
      "country": "AT",
      "start_date": "2025-01-01",
      "end_date": "2025-01-31"
    }
  ]
}
```

## Local dashboard (Streamlit + Athena)

`scripts/app.py` queries Athena table `entsoe.generation_clean` in region `eu-west-2`.

Install local dependencies (example):

```bash
pip install streamlit pandas plotly pyathena
```

Run:

```bash
streamlit run scripts/app.py
```

## Local extraction script

`entsoe_job/entsoe-analysis/entsoe_multiday_1VjEIZ.py` is a local utility that:

- Loads `entsoe_job/entsoe-analysis/config.json`
- Pulls ENTSO-E data day-by-day
- Flattens columns and exports CSV into `Data/`

Run from repo root:

```bash
export ENTSOE_API_KEY="your-token"
python entsoe_job/entsoe-analysis/entsoe_multiday_1VjEIZ.py
```

## Operational notes

- ENTSO-E can return 429/5xx intermittently; backfill Lambda includes retry/backoff.
- Daily Lambda currently has no custom retry wrapper around ENTSO-E calls.
- Re-running the same day is idempotent at object key level (same key overwrite).
- Keep ENTSO-E tokens in secrets management for production deployments.

## Security

Use least-privilege IAM roles for:

- Lambda execution role (`trust-policy.json`).
- Step Functions execution role (`trust-policy-step.json`, `entsoe_worker/sf-trust.json`).
- EventBridge Scheduler role (`trust-policy-scheduler.json`).

## Known caveat

`scripts/run_backfill.sh` currently sends `country/year/month` inputs. The backfill Lambda and state machine in this repo are date-range based. Update the script input format before using it in production.

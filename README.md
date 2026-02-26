# ENTSO-E Serverless Data Lake

Serverless ingestion and analytics platform for European electricity generation data.

## Architecture

EventBridge → Step Functions → Lambda (fan-out) → S3 (Parquet partitioned) → Glue → Athena

## Features

- Event-driven daily ingestion
- Historical backfill orchestration
- Partitioned S3 lake (country/year/month/day)
- PyArrow-based Parquet storage
- Retry logic for ENTSO-E instability
- IAM-first security model

## Deploy

See /scripts and /layer build scripts.
# Chat5.2: 
- What I believe @ 20260529 to be the relevant vibe-build chat:
    - https://chatgpt.com/g/g-p-69984a12b5d881919bb92094f885a880/c/69984a2e-1d00-8390-8dd9-9dcdaae87dd0


# NOTE ON PRESENCE OF TWO READMEs

On 20260529 EP produced a second README for this project because it's been unclear which repo was current--"entsoe" or "entsoe-analysis". EP finally determined that it's probably repo "entsoe" given that the latest commits, in 20260200, appear to reflect a more professionalised, Git-committed approach without N62s etc. EP moved repo "entso-analysis" to folder "ARCHIVE" in repo.

This is a fresh README from the Chat5.2 thread above. I think it represents the latest version of the project.

# ENTSO-E Serverless Data Lake on AWS

A serverless AWS data platform for ingesting, storing, querying, and exporting ENTSO-E electricity generation data for selected European countries.

This project currently focuses on Germany (`DE`) and Austria (`AT`), with an architecture designed to scale to additional countries over time.

---

## Project summary

This project fetches ENTSO-E generation data via API, stores it in a partitioned Parquet data lake on Amazon S3, catalogs it for analytics, and makes it queryable through Athena and usable in downstream dashboards and exports.

It includes:

- **daily ingestion** for fresh T-1 data
- **historical backfill** over arbitrary date ranges
- **serverless orchestration**
- **Parquet-based lake storage**
- **Athena/Glue-based analytics access**
- **schema normalization for stable querying**

### Architecture overview

```text
[ENTSO-E API] → [AWS Lambda daily/backfill worker] → [Amazon S3 partitioned Parquet lake]
                            ↓
                     [AWS Step Functions orchestration]
                            ↓
                 [AWS Glue Data Catalog / Athena table]
                            ↓
             [Amazon Athena SQL analytics / Streamlit dashboard]
```

In this system:

- the ingestion workers fetch ENTSO-E data and write partitioned Parquet to S3
- Glue/Athena expose that Parquet as queryable analytics tables
- the Streamlit app queries Athena with PyAthena and visualises the results

### Outcome

You have successfully:

- built a **serverless ingestion pipeline**
- **backfilled historical data**
- **converted to Parquet**
- **published the correct dependency layer**
- **fixed binary runtime mismatch**
- **orchestrated with Step Functions**

---

## Architecture

```text
ENTSO-E API
    ↓
AWS Lambda (daily worker / backfill worker)
    ↓
Amazon S3 (partitioned Parquet lake)
    ↓
AWS Glue Data Catalog / Athena external table
    ↓
Amazon Athena SQL analytics
    ↓
QuickSight / exports / downstream analyst tooling
```

### Daily ingestion path

```text
EventBridge Scheduler
    ↓
Step Functions orchestrator (or direct Lambda trigger)
    ↓
entsoe-worker
    ↓
S3: country=XX/year=YYYY/month=MM/day=DD/data.parquet
```

### Historical backfill path

```text
Manual or Step Functions execution
    ↓
entsoe-backfill-worker
    ↓
S3: country=XX/year=YYYY/month=MM/day=DD/data.parquet
```

---

## AWS services used

- **AWS Lambda**
  - Daily ingestion worker
  - Historical backfill worker
- **Amazon EventBridge / Scheduler**
  - Daily schedule trigger
- **AWS Step Functions**
  - Map-based orchestration across countries / backfill tasks
- **Amazon S3**
  - Partitioned Parquet data lake
- **AWS Glue Data Catalog**
  - Catalog metadata
- **Amazon Athena**
  - SQL querying over Parquet data
- **CloudWatch Logs**
  - Runtime diagnostics and observability
- **IAM**
  - Role-based permissions
- **Lambda Layers**
  - Shared Python dependencies
- **Docker**
  - Runtime-matched dependency packaging for Lambda compatibility

---

## Data layout

Data is stored in S3 using Hive-style partitions:

```text
s3://entsoe-generation-data-801886451424/entsoe/generation/
  country=DE/
    year=2026/
      month=03/
        day=06/
          data.parquet
```

This partitioning supports efficient Athena pruning by:

- `country`
- `year`
- `month`
- `day`

---

## Key engineering decisions

### 1. Parquet instead of CSV
The pipeline was migrated from CSV to Parquet because Parquet is:

- columnar
- smaller
- faster for Athena
- better suited to analytics workloads

### 2. Day-partitioned storage
Daily files were chosen over monthly rewrites because day partitions are:

- more scalable
- easier to backfill safely
- more robust for retries and reruns
- more Athena-friendly for date-constrained queries

### 3. Serverless orchestration
Step Functions was used to orchestrate country-level fan-out and backfills rather than relying on fragile long-running scripts.

### 4. Runtime-matched dependency layer
Pandas / NumPy / PyArrow were packaged into a Lambda Layer using a Docker image matching the Lambda Python runtime to avoid binary mismatch issues.

---

## Problems solved during development

### Binary runtime mismatch
A Lambda import error occurred due to compiled dependency mismatch (`numpy` / `pandas`).  
This was fixed by building the dependency layer inside a runtime-matched Docker environment.

### CSV / Parquet schema drift
During development, the lake briefly contained:

- CSV files
- monthly Parquet files
- daily Parquet files

This created metadata drift and duplicate-column problems in Glue/Athena.

### Athena null-valued numeric columns
Athena initially returned timestamps and partitions correctly but numeric columns as `NULL`.  
Root cause: Parquet column names used title case with spaces, while Athena expected underscore-normalized names.

This was fixed by:

- rewriting existing Parquet files in S3 to normalize column names
- updating both Lambdas to write normalized underscore column names going forward
- recreating the Athena table manually
- avoiding further crawler-driven schema drift

### ENTSO-E throttling / long backfills
Large historical backfills hit ENTSO-E throttling and Lambda timeouts.  
The pipeline was made restart-safe and idempotent so reruns/redrives could safely continue from previously written partitions.

---

## Dependency layer

The Lambda layer contains dependencies such as:

- `pandas`
- `numpy`
- `pyarrow`
- `entsoe-py`
- related transitive packages

The layer was built in a Lambda-compatible environment to ensure the compiled wheels matched the deployed runtime.

---

## Lambda functions

### `entsoe-worker`
Daily ingestion Lambda.

Purpose:
- pull yesterday’s ENTSO-E generation data for one country
- normalize columns
- write one Parquet file to the correct day partition

Expected event shape:

```json
{
  "country": "DE"
}
```

### `entsoe-backfill-worker`
Historical backfill Lambda.

Purpose:
- pull ENTSO-E generation data for one country over a specified date range
- write one Parquet file per day
- skip already existing files unless overwrite is enabled

Expected event shape:

```json
{
  "country": "DE",
  "start_date": "2023-01-01",
  "end_date": "2026-03-06"
}
```

---

## Step Functions

Step Functions is used for controlled orchestration, especially for backfill.

Typical payload:

```json
{
  "tasks": [
    {
      "country": "DE",
      "start_date": "2023-01-01",
      "end_date": "2026-03-06"
    },
    {
      "country": "AT",
      "start_date": "2023-01-01",
      "end_date": "2026-03-06"
    }
  ]
}
```

The state machine uses a `Map` state with controlled `MaxConcurrency` to avoid overloading the ENTSO-E API.

---

## Athena table strategy

Because Glue crawlers introduced duplicate-column drift during development, the stable approach is:

- define the Athena external table manually
- use `MSCK REPAIR TABLE` to register partitions
- avoid recurring crawler-based schema inference for this dataset

This produces a more predictable analytics surface for:

- SQL queries
- dashboarding
- CSV exports
- analyst self-service tools

---

## Observability

CloudWatch logging was added to validate:

- country received
- query window used
- whether a DataFrame was returned
- DataFrame shape
- final S3 key written

Example runtime signals included:

- `COUNTRY: DE`
- `WINDOW: 2026-03-06 00:00:00+01:00 -> 2026-03-07 00:00:00+01:00`
- `DF_EMPTY: False`
- `DF_SHAPE: (96, 17)`
- `Uploaded to S3: .../data.parquet`

This confirmed successful pulls and helped distinguish data issues from metadata issues.

---

## Current state

The project now supports:

- daily Parquet ingestion
- historical backfill over arbitrary ranges
- partitioned storage in S3
- Athena querying
- stable underscore-normalized column names
- a clean path toward dashboarding and analyst CSV export

---

## Example Athena query

```sql
SELECT
  date,
  solar_actual_aggregated,
  wind_onshore_actual_aggregated
FROM entsoe.generation
WHERE country = 'DE'
  AND year = '2026'
  AND month = '03'
  AND day = '06'
LIMIT 20;
```

---

## Planned next steps

Potential next extensions include:

- analyst-facing CSV export mini-app
- QuickSight dashboards
- curated Athena views for energy-mix analysis
- country comparison dashboards
- renewable share metrics
- more countries
- improved partition management / projection
- lightweight internal API for filtered exports

---

## Security notes

This project should be operated with:

- IAM users / roles / Identity Center users
- least-privilege access
- no use of AWS root for analyst access

---

## Repo intent

This repository documents a practical AWS-based energy analytics pipeline that demonstrates:

- cloud-native data engineering
- serverless orchestration
- data lake design
- backfill strategy
- Athena analytics enablement
- schema normalization and operational debugging

It is intended both as a working analytics platform and as a portfolio-grade example of production-style AWS data engineering.

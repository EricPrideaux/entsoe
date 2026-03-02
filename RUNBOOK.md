# ENTSO-E Pipeline Runbook

Operational runbook for the ENTSO-E serverless ingestion process.

## Scope

This runbook covers:

- Daily ingestion operations
- Historical backfill operations
- Monitoring and triage
- Recovery procedures

## System overview

- Scheduler triggers Step Functions state machine `entsoe-country-orchestrator`.
- State machine fans out countries and invokes Lambda `entsoe-worker`.
- Lambda writes parquet to S3 partition path:
  - `entsoe/generation/country=XX/year=YYYY/month=MM/day=DD/data.parquet`
- Backfills run via state machine `entsoe-backfill` and Lambda `entsoe-backfill-worker`.

## Preconditions

- AWS CLI configured to the correct account and region.
- Region set to `eu-west-2` (or override in commands).
- Required environment in both Lambdas:
  - `BUCKET_NAME`
  - `ENTSOE_API_KEY`
- Backfill Lambda optional:
  - `OVERWRITE=true|false`

## Daily operations

### 1. Check scheduler status

```bash
aws scheduler list-schedules --region eu-west-2
```

```bash
aws scheduler get-schedule \
  --name <schedule-name> \
  --group-name default \
  --region eu-west-2
```

Expected: schedule is enabled and target points to the daily state machine.

### 2. Verify recent Step Functions executions

```bash
aws stepfunctions list-executions \
  --state-machine-arn arn:aws:states:eu-west-2:801886451424:stateMachine:entsoe-country-orchestrator \
  --max-results 10 \
  --region eu-west-2
```

Expected: latest execution status is `SUCCEEDED`.

### 3. Verify daily partitions landed in S3

```bash
aws s3 ls s3://<bucket>/entsoe/generation/country=DE/year=YYYY/month=MM/day=DD/ --region eu-west-2
```

```bash
aws s3 ls s3://<bucket>/entsoe/generation/country=AT/year=YYYY/month=MM/day=DD/ --region eu-west-2
```

Expected: `data.parquet` exists for each country.

### 4. Verify queryability in Athena

If needed, refresh partitions:

```sql
MSCK REPAIR TABLE entsoe.generation_clean;
```

Validation query:

```sql
SELECT country, date, COUNT(*) AS rows
FROM entsoe.generation_clean
WHERE date = DATE 'YYYY-MM-DD'
GROUP BY 1,2
ORDER BY 1;
```

Expected: rows exist for expected countries.

## Manual daily run (on-demand)

Start an ad hoc ingestion execution:

```bash
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:eu-west-2:801886451424:stateMachine:entsoe-country-orchestrator \
  --input '{"countries":["DE","AT"]}' \
  --region eu-west-2
```

Track status:

```bash
aws stepfunctions describe-execution \
  --execution-arn <execution-arn> \
  --region eu-west-2
```

## Backfill operations

Important: `scripts/run_backfill.sh` currently sends `country/year/month` input, but the backfill flow expects date ranges. Use CLI examples below unless script is fixed.

### 1. Start backfill state machine with date-range tasks

```bash
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:eu-west-2:801886451424:stateMachine:entsoe-backfill \
  --input '{
    "tasks":[
      {"country":"DE","start_date":"2025-01-01","end_date":"2025-01-31"},
      {"country":"AT","start_date":"2025-01-01","end_date":"2025-01-31"}
    ]
  }' \
  --region eu-west-2
```

### 2. Monitor backfill execution

```bash
aws stepfunctions describe-execution \
  --execution-arn <execution-arn> \
  --region eu-west-2
```

### 3. Validate backfill completeness

- Confirm S3 partitions for all expected days.
- Run Athena row-count checks by `country` and `date`.
- Investigate partial failures using Step Functions history and Lambda logs.

## Incident triage

### Symptom: Step Functions execution failed

Checks:

- `describe-execution` for failure output.
- `get-execution-history` for failing state/task.
- Lambda CloudWatch logs for traceback.

Common causes:

- ENTSO-E transient `429/5xx`
- Missing/invalid `ENTSOE_API_KEY`
- S3 permissions denied
- Invalid state machine input shape

### Symptom: Lambda success but no data in S3

Checks:

- Log line showing `No data for <country>` (normal for some dates).
- Verify target date logic (`yesterday` UTC).
- Confirm bucket/env var values and S3 path prefix.

### Symptom: Athena shows missing dates

Checks:

- Ensure parquet exists in S3 for that partition.
- Run `MSCK REPAIR TABLE`.
- Verify Glue table location matches S3 prefix.

## Recovery procedures

### Re-run a failed day

- Re-run daily orchestrator (idempotent object overwrite for same partition key).
- Or run backfill for a single-day range:
  - `start_date == end_date`

Example:

```bash
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:eu-west-2:801886451424:stateMachine:entsoe-backfill \
  --input '{"tasks":[{"country":"DE","start_date":"2025-02-15","end_date":"2025-02-15"}]}' \
  --region eu-west-2
```

### Widespread ENTSO-E instability

- Delay retries and rerun in batches.
- Prefer backfill Lambda path (includes retry/backoff logic).
- Keep country/task concurrency controlled (`MaxConcurrency` currently 5).

## Change management checklist

Before production changes:

- Confirm IAM trust and permissions for Lambda, Step Functions, Scheduler.
- Validate state machine JSON changes in a non-prod execution.
- Verify environment variables on both worker Lambdas.
- Run a smoke ingestion for one country/day.
- Confirm S3 object and Athena query success.

After deployment:

- Check first scheduled execution status.
- Verify S3 partitions for each country.
- Run Athena validation query.

## Useful commands

List recent Lambda logs:

```bash
aws logs tail /aws/lambda/entsoe-worker --since 1h --region eu-west-2
```

```bash
aws logs tail /aws/lambda/entsoe-backfill-worker --since 1h --region eu-west-2
```

Execution history:

```bash
aws stepfunctions get-execution-history \
  --execution-arn <execution-arn> \
  --max-results 100 \
  --region eu-west-2
```

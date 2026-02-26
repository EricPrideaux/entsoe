#!/bin/bash

# Backfill ENTSO-E generation data
# Usage: ./run_backfill.sh 2025 2026

START_YEAR=$1
END_YEAR=$2

COUNTRIES=("DE" "AT")
STATE_MACHINE_ARN="arn:aws:states:eu-west-2:801886451424:stateMachine:entsoe-backfill"
REGION="eu-west-2"

for country in "${COUNTRIES[@]}"
do
  for ((y=$START_YEAR; y<=$END_YEAR; y++))
  do
    for m in {1..12}
    do
      echo "Starting backfill for $country $y-$m"

      aws stepfunctions start-execution \
        --state-machine-arn $STATE_MACHINE_ARN \
        --input "{\"country\":\"$country\",\"year\":$y,\"month\":$m}" \
        --region $REGION

      sleep 0.5
    done
  done
done

echo "Backfill triggered."
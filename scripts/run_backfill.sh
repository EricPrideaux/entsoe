'''
From Chat: https://chatgpt.com/g/g-p-69984a12b5d881919bb92094f885a880/c/69984a2e-1d00-8390-8dd9-9dcdaae87dd0
Search "Example of a production-quality version."
''' 

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
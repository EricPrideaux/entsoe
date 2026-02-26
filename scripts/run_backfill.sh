for country in DE AT
do
  for y in 2025 2026
  do
    for m in {1..12}
    do
      # Stop after current month (adjust if needed)
      if [ "$y" -eq 2026 ] && [ "$m" -gt 2 ]; then break; fi

      aws stepfunctions start-execution \
        --state-machine-arn arn:aws:states:eu-west-2:801886451424:stateMachine:entsoe-backfill \
        --input "{\"country\":\"$country\",\"year\":$y,\"month\":$m}" \
        --region eu-west-2

      sleep 0.5
    done
  done
dones
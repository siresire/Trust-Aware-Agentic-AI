#!/bin/bash
# collect_sessions.sh - record many sessions one after another, unattended.
# Usage (from anywhere):  sudo bash experiments/collect_sessions.sh FIRST LAST
# Stop politely:          touch data/STOP     (stops before the next session)

cd "$(dirname "$0")/.." || exit 1            # always work from the project root
FIRST=${1:?usage: collect_sessions.sh FIRST LAST}
LAST=${2:?usage: collect_sessions.sh FIRST LAST}
mkdir -p data
LOG=data/collect.log

for s in $(seq "$FIRST" "$LAST"); do
    if [ -f data/STOP ]; then
        echo "$(date '+%F %T') STOP file found, ending before session $s" | tee -a "$LOG"
        break
    fi
    dir=$(printf 'data/raw/session_%03d' "$s")
    if [ -d "$dir" ]; then
        echo "$(date '+%F %T') session $s already exists, skipped" | tee -a "$LOG"
        continue
    fi
    echo "$(date '+%F %T') session $s start" | tee -a "$LOG"
    python3 -m experiments.run_experiment --session "$s" > "data/collect_$s.out" 2>&1
    echo "$(date '+%F %T') session $s end (exit code $?)" | tee -a "$LOG"
    sleep 10                                 # let the machine settle between sessions
done
echo "$(date '+%F %T') collection finished" | tee -a "$LOG"
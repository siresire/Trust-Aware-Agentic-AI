#!/bin/bash
# run_agent_sessions.sh - the experiment: the same event sessions under three modes.
# For every seed and every mode: start a labelled session (experiments.run_experiment),
# start the agent 40 s later in that mode, stop the agent when the session ends.
# The seed decides the events and the traffic, so every mode faces exactly the same session.
#
# Usage (from anywhere):   sudo bash experiments/run_agent_sessions.sh
# Short test:              sudo DURATION=300 SEEDS=799 MODES=trust bash experiments/run_agent_sessions.sh
# Stop politely:           touch data/STOP   (stops before the next run)

cd "$(dirname "$0")/.." || exit 1            # always work from the project root
SEEDS=${SEEDS:-"701 702 703"}
MODES=${MODES:-"none predict trust"}
DURATION=${DURATION:-1800}                   # seconds per session (30 min)
OUT=data/experiment
mkdir -p "$OUT"
LOG=$OUT/runs.log

si=0
for seed in $SEEDS; do
    si=$((si + 1))
    mi=0
    for mode in $MODES; do
        case $mode in none) mi=0;; predict) mi=1;; trust) mi=2;; esac
        session=$((300 + 10 * mi + si))      # none 301.., predict 311.., trust 321..
        if [ -f data/STOP ]; then
            echo "$(date '+%F %T') STOP file found, ending" | tee -a "$LOG"
            exit 0
        fi
        if [ -d "$(printf 'data/raw/session_%03d' "$session")" ]; then
            echo "$(date '+%F %T') session $session already exists, skipped" | tee -a "$LOG"
            continue
        fi
        echo "$(date '+%F %T') session $session  seed $seed  mode $mode  start" | tee -a "$LOG"

        python3 -m experiments.run_experiment --session "$session" --seed "$seed" \
            --duration "$DURATION" > "$OUT/session_${session}.out" 2>&1 &
        RUN=$!
        sleep 40                             # network up, fresh logs, a little history
        .venv/bin/python -m agent.run_agent --mode "$mode" \
            --log "$OUT/agent_${session}_${mode}.jsonl" > "$OUT/agent_${session}_${mode}.out" 2>&1 &
        AGENT=$!

        wait "$RUN"                          # the session decides when the run is over
        kill "$AGENT" 2>/dev/null
        wait "$AGENT" 2>/dev/null
        echo "$(date '+%F %T') session $session  seed $seed  mode $mode  end" | tee -a "$LOG"
        sleep 10                             # let the machine settle
    done
done
echo "$(date '+%F %T') experiment finished" | tee -a "$LOG"
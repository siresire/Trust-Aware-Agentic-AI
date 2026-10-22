# Results

## Table 1: what each policy did (all three sessions together)

| | No agent | Prediction-only | Trust-aware |
|---|---|---|---|
| Jams (events) | 19 | 25 | 25 |
| Jams acted on | 0% | 100% | 100% |
| Time to first slow-down (median, s) | - | 9.5 | 5.7 |
| Slow-downs during jams that hit a flooder | - | 55% | 84% |
| Faults (events) | 5 | 11 | 11 |
| Faults with a wrong slow-down | 0% | 91% | 18% |
| Device-seconds slowed during faults | 0 | 1057 | 213 |
| Calm time (hours) | 0.29 | 0.76 | 0.49 |
| Slow-downs in calm time (per hour) | 0.0 | 149.8 | 18.2 |

## Table 2: protected devices during events (share of readings that were bad)

| Event type | No agent | Prediction-only | Trust-aware |
|---|---|---|---|
| C_SEVERE | 96% bad | 17% bad | 42% bad |
| C_BORDER | 79% bad | 11% bad | 22% bad |
| F_WAN | 90% bad | 85% bad | 86% bad |
| F_DEVLINK | 13% bad | 13% bad | 18% bad |

## Table 3: the trust-aware agent's diagnosis

| Event type | Events | Named right | Named as (count) |
|---|---|---|---|
| C_SEVERE | 12 | 100% | jam 12 |
| C_BORDER | 13 | 100% | jam 13 |
| F_WAN | 3 | 100% | internet fault 3 |
| F_DEVLINK | 8 | 100% | device fault 8 |

Homeowner messages in calm time: 28 in 0.49 h (56.6 per hour)

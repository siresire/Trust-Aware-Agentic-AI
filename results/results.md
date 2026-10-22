# Results

Runs from data/experiment2

## Table 1: what each policy did (all three sessions together)

| | No agent | Prediction-only | Trust-aware |
|---|---|---|---|
| Jams (events) | 25 | 25 | 25 |
| Jams acted on | 0% | 100% | 96% |
| Time to first slow-down (median, s) | - | 4.3 | 4.8 |
| Slow-downs during jams that hit a flooder | - | 56% | 94% |
| Faults (events) | 11 | 11 | 11 |
| Faults with a wrong slow-down | 0% | 100% | 18% |
| Device-seconds slowed during faults | 0 | 1045 | 259 |
| Calm time (hours) | 0.71 | 0.76 | 0.69 |
| Slow-downs in calm time (per hour) | 0.0 | 133.8 | 11.6 |

## Table 2: protected devices during events (share of readings that were bad)

| Event type | No agent | Prediction-only | Trust-aware |
|---|---|---|---|
| C_SEVERE | 96% bad | 21% bad | 41% bad |
| C_BORDER | 73% bad | 4% bad | 12% bad |
| F_WAN | 86% bad | 85% bad | 87% bad |
| F_DEVLINK | 11% bad | 10% bad | 12% bad |

## Table 3: the trust-aware agent's diagnosis

| Event type | Events | Named right | Named as (count) |
|---|---|---|---|
| C_SEVERE | 12 | 100% | jam 12 |
| C_BORDER | 13 | 69% | jam 9, ok 2, device fault 2 |
| F_WAN | 3 | 100% | internet fault 3 |
| F_DEVLINK | 8 | 88% | device fault 7, ok 1 |

Homeowner messages in calm time: 18 in 0.69 h (26.1 per hour)

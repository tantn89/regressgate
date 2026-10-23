Share of 1000 simulated CI runs that fail, per gate. 20 cases: 12 stable, 4 at 95%, 4 flaky (50-80%). In the 'no change' rows every failure is a false alarm; in the others every pass is a missed regression.

| Scenario | Trials per case | Naive (any drop) | Tolerance (> 5 pp) | regressgate |
|---|---|---|---|---|
| no change | 1 | 35% | 13% | 0% |
| no change | 3 | 43% | 9% | 1% |
| no change | 5 | 44% | 5% | 2% |
| no change | 10 | 48% | 1% | 2% |
| one stable case breaks (-5 pp) | 1 | 61% | 36% | 0% |
| one stable case breaks (-5 pp) | 3 | 86% | 45% | 9% |
| one stable case breaks (-5 pp) | 5 | 91% | 42% | 92% |
| one stable case breaks (-5 pp) | 10 | 98% | 46% | 99% |
| stable cases drop to 85% (-9 pp) | 1 | 76% | 56% | 3% |
| stable cases drop to 85% (-9 pp) | 3 | 94% | 73% | 25% |
| stable cases drop to 85% (-9 pp) | 5 | 98% | 78% | 46% |
| stable cases drop to 85% (-9 pp) | 10 | 100% | 90% | 83% |

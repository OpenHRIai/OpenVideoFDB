# OpenVideoFDB summary

Runs: runs/gt, runs/random  
Judge: gpt-4o. n = manifest rows (clip, bucket) scored. Overall = mean of each perception row's available judge axes. Brackets are 95 % bootstrap CIs over rows (1000 resamples, seed 0). TOR-Align % = fraction of timed rows whose takeover matches the expected class; latency is the median.

| provider | mode | n | Fluency | Conv. Flow | Grounding | Overall | TOR-Align % | Latency ms |
|---|---|---|---|---|---|---|---|---|
| human_gt | av | 60 | 3.55 [2.70, 4.25] | 4.90 [4.70, 5.00] | 3.80 [3.30, 4.20] | 3.95 [3.40, 4.45] | 70 [55, 82] | 588 [374, 856] |
| random | av | 60 | 1.95 [1.00, 2.85] | 3.10 [1.60, 4.50] | 1.60 [1.00, 2.10] | 2.15 [1.27, 2.98] | 28 [15, 42] | 338 [0, 1219] |

## Per dynamic

| provider | mode | dynamic_type | n | Fluency | Conv. Flow | Grounding | Overall | TOR-Align % | Latency ms |
|---|---|---|---|---|---|---|---|---|---|
| human_gt | av | Laughter | 20 | 2.60 [1.60, 3.50] | — | 3.80 [3.30, 4.20] | 3.20 [2.55, 3.80] | — | — |
| human_gt | av | Pause Handling | 10 | 4.50 [3.50, 5.00] | 4.90 [4.70, 5.00] | — | 4.70 [4.10, 5.00] | 100 [100, 100] | 918 [918, 918] |
| human_gt | av | Turn-taking | 10 | — | — | — | — | 50 [20, 80] | 786 [588, 1098] |
| human_gt | av | Verbal Backchanneling | 10 | — | — | — | — | 40 [10, 70] | 160 [0, 264] |
| human_gt | av | Verbal Interruption | 10 | — | — | — | — | 90 [70, 100] | 472 [353, 907] |
| random | av | Laughter | 20 | 0.90 [0.30, 1.50] | — | 1.60 [1.00, 2.10] | 1.25 [0.80, 1.70] | — | — |
| random | av | Pause Handling | 10 | 3.00 [1.50, 4.50] | 3.10 [1.60, 4.50] | — | 3.05 [1.55, 4.50] | 70 [40, 90] | 118 [0, 1580] |
| random | av | Turn-taking | 10 | — | — | — | — | 30 [10, 60] | 0 [0, 858] |
| random | av | Verbal Backchanneling | 10 | — | — | — | — | 0 [0, 0] | — |
| random | av | Verbal Interruption | 10 | — | — | — | — | 10 [0, 30] | 3420 [440, 3921] |

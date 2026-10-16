# OpenVideoFDB summary

Runs: runs/gt, runs/random  
Judge: gpt-4o. n = manifest rows (clip, bucket) scored. Overall = mean of each perception row's available judge axes. Brackets are 95 % bootstrap CIs over rows (1000 resamples, seed 0). TOR-Align % = fraction of timed rows whose takeover matches the expected class; latency is the median.

| provider | mode | n | Fluency | Conv. Flow | Grounding | Overall | TOR-Align % | Latency ms |
|---|---|---|---|---|---|---|---|---|
| human_gt | av | 60 | 3.40 [2.70, 4.05] | 4.20 [3.00, 5.00] | 3.80 [3.50, 4.10] | 3.70 [3.10, 4.25] | 100 [100, 100] | 508 [304, 652] |
| random | av | 60 | 2.00 [1.05, 2.90] | 3.00 [1.50, 4.50] | 1.50 [1.00, 1.90] | 2.12 [1.25, 2.93] | 35 [22, 50] | 40 [0, 2176] |

## Per dynamic

| provider | mode | dynamic_type | n | Fluency | Conv. Flow | Grounding | Overall | TOR-Align % | Latency ms |
|---|---|---|---|---|---|---|---|---|---|
| human_gt | av | Laughter | 20 | 2.90 [2.20, 3.60] | — | 3.80 [3.50, 4.10] | 3.35 [2.85, 3.80] | — | — |
| human_gt | av | Pause Handling | 10 | 3.90 [2.50, 5.00] | 4.20 [3.00, 5.00] | — | 4.05 [2.75, 5.00] | 100 [100, 100] | 1016 [1000, 1032] |
| human_gt | av | Turn-taking | 10 | — | — | — | — | 100 [100, 100] | 632 [456, 1032] |
| human_gt | av | Verbal Backchanneling | 10 | — | — | — | — | 100 [100, 100] | 304 [270, 304] |
| human_gt | av | Verbal Interruption | 10 | — | — | — | — | 100 [100, 100] | 636 [516, 900] |
| random | av | Laughter | 20 | 1.00 [0.50, 1.50] | — | 1.50 [1.00, 1.90] | 1.25 [0.85, 1.65] | — | — |
| random | av | Pause Handling | 10 | 3.00 [1.50, 4.50] | 3.00 [1.50, 4.50] | — | 3.00 [1.50, 4.50] | 80 [50, 100] | 196 [0, 2176] |
| random | av | Turn-taking | 10 | — | — | — | — | 50 [20, 80] | 0 [0, 968] |
| random | av | Verbal Backchanneling | 10 | — | — | — | — | 0 [0, 0] | — |
| random | av | Verbal Interruption | 10 | — | — | — | — | 10 [0, 30] | 2904 [0, 4133] |

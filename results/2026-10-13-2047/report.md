# Netpulse sweep report, 2026-10-13 20:47

## Setup

- **Date**: 2026-10-13 20:47
- **Path**: UDP over loopback (127.0.0.1), client and echo server on the same machine
- **Machine**: not recorded
- **Code version**: 5dd2489 (Phase 3), run before it was committed
- **Rates**: 13 targets from 1,000 to 200,000 pps
- **Runs**: 3 per rate, 2 seconds each, 1 second pause between runs

## Findings

- **The knee is between 80,000 and 100,000 pps.** Below it the path keeps up; from 100,000 pps it is saturated.
- **Healthy up to 50,000 pps**: no loss, best p50 of 34 µs and best p99 of 83 µs.
- **The tail degrades first.** At 80,000 pps p99 is already 1.8 ms while p50 is still 40 µs and the median run loses nothing.
- **Once saturated**, p50 is 22.5 ms to 41.9 ms, about 1,300 times the best p50, and 1.5% to 11.3% of packets are lost.
- **Unstable rates**: 80,000 (1 of 3 runs saturated), 100,000 (2 of 3 runs saturated). At these rates the path tips into saturation in some runs and not others, so the knee is a range, not a point.
- **The sender tops out near 110,000 pps.** From 120,000 pps up it cannot reach the target, so those rates land on roughly the same point of the plot.
- **Jitter was not measured in this sweep** (it predates Phase 4).

![Latency, jitter and loss against send rate](sweep.png)

## Results by rate

Each row is the median of that rate's runs. ⚠ marks an unstable rate, where some runs lost packets and others did not. Every individual run is in `sweep.csv`.

| Target pps | Achieved pps | Loss | p50 | p95 | p99 |
|---|---|---|---|---|---|
| 1,000 | 1,000 | 0.00% | 110 µs | 126 µs | 133 µs |
| 2,000 | 2,000 | 0.00% | 116 µs | 130 µs | 132 µs |
| 5,000 | 5,000 | 0.00% | 34 µs | 54 µs | 108 µs |
| 10,000 | 10,000 | 0.00% | 34 µs | 42 µs | 83 µs |
| 20,000 | 20,000 | 0.00% | 34 µs | 40 µs | 93 µs |
| 50,000 | 50,003 | 0.00% | 34 µs | 40 µs | 98 µs |
| 80,000 ⚠ | 80,035 | 0.00% | 40 µs | 78 µs | 1.8 ms |
| 100,000 ⚠ | 100,033 | 1.54% | 22.5 ms | 41.4 ms | 42.5 ms |
| 120,000 | 110,450 | 8.47% | 41.9 ms | 44.1 ms | 46.2 ms |
| 140,000 | 103,189 | 8.45% | 40.9 ms | 47.3 ms | 50.3 ms |
| 160,000 | 110,184 | 10.37% | 41.1 ms | 46.6 ms | 47.9 ms |
| 180,000 | 111,722 | 11.27% | 41.4 ms | 45.0 ms | 46.6 ms |
| 200,000 | 111,968 | 11.07% | 41.1 ms | 43.4 ms | 45.3 ms |

## How to read this

- **p50, p95, p99**: sort every round-trip time (RTT) in a run. p50 is the middle one, so half the packets were faster. p99 is the one 99% of packets beat, so it shows the slowest 1%, the tail.
- **Jitter** is how much the delay changes from one packet to the next. Percentiles cannot show this, because they ignore the order packets arrived in. *Jitter (mean)* averages the change between every pair of consecutive packets over the whole run. *Jitter (RFC 3550)* is the running estimate from the RTP standard, which moves 1/16 of the way towards each new change, so it mostly reflects the end of the run. Both use round trips rather than one-way delays, because the client only knows when a packet left and came back.
- **Longest loss burst** is the most packets lost in a row. 1,000 losses spread out and 1,000 in one gap are very different for an application.
- **The rules behind the findings**: the tail has degraded when p99 is more than 10 times its best value in the sweep. A run is saturated when it loses packets or its p50 is more than 10 times the best p50 in the sweep, and a rate is saturated when its median run is. A rate is unstable when some of its runs are saturated and others are not. The sender has fallen short when it achieves less than 95% of the target rate.

## Limitations

- **Loopback, not a real network.** No cable, no router: the bottleneck is how fast this machine moves packets between two programs.
- **Client and server share one machine**, so they compete for the same CPU. A heavy client can slow the server it is measuring.
- **Results vary between runs and between days**, depending on what else the machine is doing and whether it is on battery. Compare reports from the same machine and conditions.
- **Low rates read slower than mid rates.** Between packets both programs go to sleep, and waking up is part of the measured time.

## Reproduce

```bash
./echo_server        # terminal 1
python3 sweep.py     # terminal 2
```

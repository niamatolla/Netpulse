# Netpulse sweep report, 2026-10-15 16:01

## Setup

- **Date**: 2026-10-15 16:01
- **Path**: UDP over loopback (127.0.0.1), client and echo server on the same machine
- **Machine**: Apple M1, 8 cores, macOS 26.6.1, on battery
- **Code version**: 8f21473 plus uncommitted changes
- **Rates**: 17 targets from 1,000 to 200,000 pps
- **Runs**: 5 per rate, 2 seconds each, 1 second pause between runs

## Findings

- **The knee is between 100,000 and 105,000 pps.** Below it the path keeps up; from 105,000 pps it is saturated.
- **Healthy up to 50,000 pps**: no loss, best p50 of 33 µs and best p99 of 66 µs.
- **The tail degrades first.** At 60,000 pps p99 is already 866 µs while p50 is still 33 µs and the median run loses nothing.
- **Once saturated**, p50 is 7.1 ms to 40.2 ms, about 1,200 times the best p50, and 0.0% to 8.8% of packets are lost. Where packets are lost, the longest loss burst per run is 8 to 13 packets in a row, against at least 11,840 lost per run, so the losses are many short gaps rather than one long one.
- **Unstable rates**: 85,000 (1 of 5 runs saturated), 95,000 (1 of 5 runs saturated). At these rates the path tips into saturation in some runs and not others, so the knee is a range, not a point.
- **The sender tops out near 110,000 pps.** From 120,000 pps up it cannot reach the target, so those rates land on roughly the same point of the plot.
- **Jitter** (mean change between consecutive round trips) ranges from 4.6 µs at 20,000 pps to 11 µs at 1,000 pps.
- **Jitter barely moves at saturation**: 5.8 µs against 7.3 µs when healthy, while p50 grows about 1,200 times. A full queue delays every packet by about the same amount, so the delay is huge but steady. Jitter alone would not reveal the knee.

![Latency, jitter and loss against send rate](sweep.png)

## Results by rate

Each row is the median of that rate's runs. ⚠ marks an unstable rate, where some runs lost packets and others did not. Every individual run is in `sweep.csv`.

| Target pps | Achieved pps | Loss | p50 | p95 | p99 | Jitter (mean) | Jitter (RFC 3550) | Longest loss burst |
|---|---|---|---|---|---|---|---|---|
| 1,000 | 1,000 | 0.00% | 131 µs | 153 µs | 166 µs | 11 µs | 13 µs | 0 |
| 2,000 | 2,000 | 0.00% | 129 µs | 151 µs | 161 µs | 11 µs | 7.2 µs | 0 |
| 5,000 | 5,000 | 0.00% | 42 µs | 88 µs | 109 µs | 8.2 µs | 6.5 µs | 0 |
| 10,000 | 10,000 | 0.00% | 41 µs | 53 µs | 66 µs | 5.7 µs | 3.6 µs | 0 |
| 20,000 | 20,000 | 0.00% | 34 µs | 53 µs | 85 µs | 4.6 µs | 1.0 µs | 0 |
| 50,000 | 50,009 | 0.00% | 34 µs | 44 µs | 304 µs | 6.5 µs | 6.0 µs | 0 |
| 60,000 | 60,021 | 0.00% | 33 µs | 51 µs | 866 µs | 5.7 µs | 4.7 µs | 0 |
| 70,000 | 70,035 | 0.00% | 35 µs | 56 µs | 462 µs | 6.1 µs | 5.3 µs | 0 |
| 80,000 | 80,044 | 0.00% | 37 µs | 210 µs | 1.7 ms | 6.9 µs | 6.6 µs | 0 |
| 85,000 ⚠ | 85,054 | 0.00% | 43 µs | 220 µs | 2.3 ms | 7.1 µs | 7.2 µs | 0 |
| 90,000 | 90,047 | 0.00% | 43 µs | 554 µs | 1.8 ms | 7.1 µs | 7.0 µs | 0 |
| 95,000 ⚠ | 95,058 | 0.00% | 44 µs | 973 µs | 2.8 ms | 6.7 µs | 7.0 µs | 0 |
| 100,000 | 100,069 | 0.00% | 49 µs | 2.6 ms | 4.7 ms | 6.0 µs | 5.0 µs | 0 |
| 105,000 | 105,076 | 0.00% | 7.1 ms | 15.4 ms | 15.9 ms | 5.6 µs | 4.0 µs | 0 |
| 110,000 | 110,075 | 5.38% | 39.5 ms | 41.4 ms | 42.3 ms | 5.7 µs | 3.5 µs | 8 |
| 120,000 | 111,892 | 7.64% | 39.9 ms | 41.3 ms | 41.9 ms | 5.8 µs | 3.4 µs | 11 |
| 200,000 | 112,308 | 8.82% | 40.2 ms | 41.9 ms | 42.8 ms | 5.8 µs | 3.8 µs | 13 |

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

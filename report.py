"""Phase 4: the written report for one sweep.

sweep.py calls write_report() after every sweep. It reads the sweep's runs and
writes report.md into the same dated folder, so each report sits next to the
data and plot it describes.

All the findings are computed from the data with fixed rules, which the report
spells out, so a report never claims something its own numbers do not show.
"""

import statistics

# Thresholds used to name the stages of the curve. They are stated in every
# report so a reader can check them against the table.
TAIL_FACTOR = 10       # p99 this many times its best value: the tail has degraded
SATURATED_FACTOR = 10  # p50 this many times its best value: the path is saturated
SENDER_SHORTFALL = 0.95  # achieved below 95% of the target: the sender could not keep up


def median_or_none(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def summarise(rows):
    """Group the runs by target rate and take the median of every column.

    Returns one dict per target rate, sorted by rate. The median is used so a
    single unusual run does not move the result.
    """
    columns = [key for key in rows[0] if key not in ("run", "target_pps")]
    summary = []
    for rate in sorted({row["target_pps"] for row in rows}):
        runs = [row for row in rows if row["target_pps"] == rate]
        point = {"target_pps": rate, "runs": len(runs)}
        for column in columns:
            point[column] = median_or_none(row[column] for row in runs)
        summary.append(point)

    # A rate is unstable when its runs disagree about being saturated: some
    # kept up, others lost packets or had p50 blow up. The path is on the edge.
    medians = [p["p50_us"] for p in summary if p["p50_us"] is not None]
    best_p50 = min(medians) if medians else None
    for point in summary:
        runs = [row for row in rows if row["target_pps"] == point["target_pps"]]
        saturated = sum(1 for row in runs if is_saturated(row, best_p50))
        point["saturated_runs"] = saturated
        point["unstable"] = 0 < saturated < len(runs)
    return summary


def is_saturated(result, best_p50):
    """A run (or a rate's medians) is saturated if it lost packets or its p50
    is more than SATURATED_FACTOR times the best p50 of the sweep."""
    if result["loss_pct"] and result["loss_pct"] > 0:
        return True
    return (result["p50_us"] is not None and best_p50 is not None
            and result["p50_us"] > SATURATED_FACTOR * best_p50)


def format_us(value):
    """A time in microseconds, shown in µs or ms, whichever reads better."""
    if value is None:
        return "–"
    if value >= 1000:
        return f"{value / 1000:.1f} ms"
    return f"{value:.0f} µs" if value >= 10 else f"{value:.1f} µs"


def format_rate(value):
    return f"{value:,.0f}"


def round_to(value, significant=2):
    """Round to a few significant figures, so 1,252 reads as 1,300."""
    return float(f"{value:.{significant}g}")


def findings(summary):
    """The headline results, as sentences, computed with the rules above."""
    lines = []
    measured = [p for p in summary if p["p50_us"] is not None]
    if not measured:
        return ["No replies came back at any rate, so there is nothing to report."]

    best_p50 = min(p["p50_us"] for p in measured)
    best_p99 = min(p["p99_us"] for p in measured)

    tail = next((p for p in measured if p["p99_us"] > TAIL_FACTOR * best_p99), None)
    saturated = next((p for p in summary if is_saturated(p, best_p50)), None)

    # The knee: between the last rate that was still fine and the first saturated one
    if saturated is None:
        lines.append("**No knee in this sweep.** The path never saturated, even at "
                     f"{format_rate(summary[-1]['target_pps'])} pps.")
    else:
        before = [p for p in summary if p["target_pps"] < saturated["target_pps"]]
        if before:
            lines.append(f"**The knee is between {format_rate(before[-1]['target_pps'])} and "
                         f"{format_rate(saturated['target_pps'])} pps.** Below it the path keeps "
                         f"up; from {format_rate(saturated['target_pps'])} pps it is saturated.")
        else:
            lines.append("**The path was already saturated at the lowest rate in the sweep.**")

    # Healthy region
    healthy = [p for p in measured
               if (saturated is None or p["target_pps"] < saturated["target_pps"])
               and (tail is None or p["target_pps"] < tail["target_pps"])]
    if healthy:
        lines.append(f"**Healthy up to {format_rate(healthy[-1]['target_pps'])} pps**: no loss, "
                     f"best p50 of {format_us(best_p50)} and best p99 of {format_us(best_p99)}.")

    # The tail moves before the median
    if tail is not None and (saturated is None or tail["target_pps"] < saturated["target_pps"]):
        lines.append(f"**The tail degrades first.** At {format_rate(tail['target_pps'])} pps "
                     f"p99 is already {format_us(tail['p99_us'])} while p50 is still "
                     f"{format_us(tail['p50_us'])} and the median run loses nothing.")

    # Saturated behaviour
    if saturated is not None:
        beyond = [p for p in summary if p["target_pps"] >= saturated["target_pps"]]
        p50s = [p["p50_us"] for p in beyond if p["p50_us"] is not None]
        losses = [p["loss_pct"] for p in beyond]
        bursts = [p["max_loss_burst"] for p in beyond if p.get("max_loss_burst") is not None]
        sentence = (f"**Once saturated**, p50 is {format_us(min(p50s))} to {format_us(max(p50s))}, "
                    f"about {round_to(max(p50s) / best_p50):,.0f} times the best p50, and "
                    f"{min(losses):.1f}% to {max(losses):.1f}% of packets are lost")
        lossy = [p for p in beyond if p["lost"] and p["lost"] > 0
                 and p.get("max_loss_burst") is not None]
        if lossy:
            bursts = [p["max_loss_burst"] for p in lossy]
            fewest_lost = min(p["lost"] for p in lossy)
            sentence += (f". Where packets are lost, the longest loss burst per run is "
                         f"{min(bursts):.0f} to {max(bursts):.0f} packets in a row")
            # Spread out: even the longest gap is a small part of what was lost
            if max(bursts) * 10 < fewest_lost:
                sentence += (f", against at least {fewest_lost:,.0f} lost per run, so the "
                             "losses are many short gaps rather than one long one")
        lines.append(sentence + ".")

    # Runs that disagree
    unstable = [p for p in summary if p["unstable"]]
    if unstable:
        rates = ", ".join(f"{format_rate(p['target_pps'])} ({p['saturated_runs']} of {p['runs']} runs saturated)"
                          for p in unstable)
        lines.append(f"**Unstable rates**: {rates}. At these rates the path tips into "
                     "saturation in some runs and not others, so the knee is a range, not a point.")

    # Sender ceiling
    short = [p for p in summary if p["achieved_pps"] < SENDER_SHORTFALL * p["target_pps"]]
    if short:
        ceiling = max(p["achieved_pps"] for p in summary)
        lines.append(f"**The sender tops out near {format_rate(round_to(ceiling))} pps.** From "
                     f"{format_rate(short[0]['target_pps'])} pps up it cannot reach the target, "
                     "so those rates land on roughly the same point of the plot.")

    # Jitter
    jitter = [p for p in measured if p.get("jitter_mean_us") is not None]
    if jitter:
        low = min(jitter, key=lambda p: p["jitter_mean_us"])
        high = max(jitter, key=lambda p: p["jitter_mean_us"])
        lines.append(f"**Jitter** (mean change between consecutive round trips) ranges from "
                     f"{format_us(low['jitter_mean_us'])} at {format_rate(low['target_pps'])} pps to "
                     f"{format_us(high['jitter_mean_us'])} at {format_rate(high['target_pps'])} pps.")

        # Jitter compared with the jump in latency once saturated
        if saturated is not None and healthy:
            calm = median_or_none(p["jitter_mean_us"] for p in healthy)
            full = median_or_none(p["jitter_mean_us"] for p in jitter
                                  if p["target_pps"] >= saturated["target_pps"])
            if calm and full and full < 3 * calm:
                lines.append(f"**Jitter barely moves at saturation**: {format_us(full)} against "
                             f"{format_us(calm)} when healthy, while p50 grows about "
                             f"{round_to(max(p50s) / best_p50):,.0f} times. A full queue "
                             "delays every packet by about the same amount, so the delay "
                             "is huge but steady. Jitter alone would not reveal the knee.")
    else:
        lines.append("**Jitter was not measured in this sweep** (it predates Phase 4).")

    return lines


def table(summary):
    has_jitter = any(p.get("jitter_mean_us") is not None for p in summary)
    header = ["Target pps", "Achieved pps", "Loss", "p50", "p95", "p99"]
    if has_jitter:
        header += ["Jitter (mean)", "Jitter (RFC 3550)", "Longest loss burst"]
    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join("---" for _ in header) + "|"]
    for p in summary:
        cells = [format_rate(p["target_pps"]) + (" ⚠" if p["unstable"] else ""),
                 format_rate(p["achieved_pps"]),
                 f"{p['loss_pct']:.2f}%",
                 format_us(p["p50_us"]), format_us(p["p95_us"]), format_us(p["p99_us"])]
        if has_jitter:
            burst = p.get("max_loss_burst")
            cells += [format_us(p.get("jitter_mean_us")), format_us(p.get("jitter_rfc_us")),
                      "–" if burst is None else f"{burst:.0f}"]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def setup_lines(meta, summary):
    def get(key):
        return meta.get(key) or "not recorded"

    if meta.get("cpu"):
        machine = (f"{meta['cpu']}, {get('cores')} cores, macOS {get('macos')}, "
                   f"{get('power')}")
    else:
        machine = "not recorded"
    return [
        f"- **Date**: {get('started')}",
        f"- **Path**: UDP over loopback (127.0.0.1), client and echo server on the same machine",
        f"- **Machine**: {machine}",
        f"- **Code version**: {get('commit')}",
        f"- **Rates**: {len(summary)} targets from {format_rate(summary[0]['target_pps'])} "
        f"to {format_rate(summary[-1]['target_pps'])} pps",
        f"- **Runs**: {get('repeats')} per rate, {get('duration_s')} seconds each, "
        f"{get('pause_s')} second pause between runs",
    ]


def write_report(folder, rows, meta):
    """Write folder/report.md for the runs in rows."""
    summary = summarise(rows)
    title_date = meta.get("started", folder.name)

    lines = [f"# Netpulse sweep report, {title_date}", ""]
    lines += ["## Setup", ""] + setup_lines(meta, summary) + [""]
    lines += ["## Findings", ""] + [f"- {line}" for line in findings(summary)] + [""]
    lines += ["![Latency, jitter and loss against send rate](sweep.png)", ""]
    lines += ["## Results by rate", "",
              "Each row is the median of that rate's runs. ⚠ marks an unstable rate, "
              "where some runs lost packets and others did not. Every individual run "
              "is in `sweep.csv`.", ""]
    lines += table(summary) + [""]
    lines += [
        "## How to read this",
        "",
        "- **p50, p95, p99**: sort every round-trip time (RTT) in a run. p50 is the "
        "middle one, so half the packets were faster. p99 is the one 99% of packets "
        "beat, so it shows the slowest 1%, the tail.",
        "- **Jitter** is how much the delay changes from one packet to the next. "
        "Percentiles cannot show this, because they ignore the order packets arrived "
        "in. *Jitter (mean)* averages the change between every pair of consecutive "
        "packets over the whole run. *Jitter (RFC 3550)* is the running estimate from "
        "the RTP standard, which moves 1/16 of the way towards each new change, so it "
        "mostly reflects the end of the run. Both use round trips rather than one-way "
        "delays, because the client only knows when a packet left and came back.",
        "- **Longest loss burst** is the most packets lost in a row. 1,000 losses "
        "spread out and 1,000 in one gap are very different for an application.",
        f"- **The rules behind the findings**: the tail has degraded when p99 is more "
        f"than {TAIL_FACTOR} times its best value in the sweep. A run is saturated "
        f"when it loses packets or its p50 is more than {SATURATED_FACTOR} times the best "
        f"p50 in the sweep, and a rate is saturated when its median run is. A rate is "
        f"unstable when some of its runs are saturated and others are not. The sender has fallen short when it achieves less than "
        f"{SENDER_SHORTFALL:.0%} of the target rate.",
        "",
        "## Limitations",
        "",
        "- **Loopback, not a real network.** No cable, no router: the bottleneck is "
        "how fast this machine moves packets between two programs.",
        "- **Client and server share one machine**, so they compete for the same CPU. "
        "A heavy client can slow the server it is measuring.",
        "- **Results vary between runs and between days**, depending on what else the "
        "machine is doing and whether it is on battery. Compare reports from the same "
        "machine and conditions.",
        "- **Low rates read slower than mid rates.** Between packets both programs go "
        "to sleep, and waking up is part of the measured time.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "./echo_server        # terminal 1",
        "python3 sweep.py     # terminal 2",
        "```",
        "",
    ]
    (folder / "report.md").write_text("\n".join(lines))

#!/usr/bin/env python3
"""Phase 3: rate sweep.

Runs ./client at each rate in RATES, several times, and records every run in
a CSV file. Then plots latency percentiles and loss against the send rate.

Every sweep gets its own pair of files, named after the time it started, so
earlier sweeps are never overwritten:

    results/sweep-2026-10-13-2047.csv
    results/sweep-2026-10-13-2047.png

The echo server must already be running:   ./echo_server
Run the sweep:                             python3 sweep.py
Redraw the plot of the latest sweep:       python3 sweep.py --plot-only
Redraw the plot of a chosen sweep:         python3 sweep.py --plot-only results/sweep-2026-10-13-2047.csv
"""

import csv
import statistics
import subprocess
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, NullFormatter

ROOT = Path(__file__).resolve().parent
CLIENT = ROOT / "client"
RESULTS_DIR = ROOT / "results"

# Send rates in packets per second. They are spaced widely where the path is healthy
# and densely from 80,000 up where it starts to saturate.
RATES = [1_000, 2_000, 5_000, 10_000, 20_000, 50_000, 80_000,
         100_000, 120_000, 140_000, 160_000, 180_000, 200_000]

DURATION_S = 2   # how long each run sends for
REPEATS = 3      # runs per rate so one unlucky run does not decide the result
PAUSE_S = 1      # rest between runs so one run's queue does not leak into the next

# Column order of the line that `./client --csv` prints
CLIENT_FIELDS = ["target_pps", "achieved_pps", "sent", "received", "lost",
                 "loss_pct", "p50_us", "p95_us", "p99_us"]
CSV_FIELDS = ["run"] + CLIENT_FIELDS

PERCENTILES = [  # column, label, colour, marker
    ("p50_us", "p50", "#2a78d6", "o"),
    ("p95_us", "p95", "#eb6834", "s"),
    ("p99_us", "p99", "#1baf7a", "^"),
]


def run_client(rate):
    """Run the client once at this rate and return its result as a dict."""
    done = subprocess.run([str(CLIENT), str(rate), str(DURATION_S), "--csv"],
                          capture_output=True, text=True)
    values = done.stdout.strip().split(",")
    if len(values) != len(CLIENT_FIELDS):
        sys.exit(f"unexpected output from client: {done.stdout!r} {done.stderr!r}")
    return dict(zip(CLIENT_FIELDS, values))


def run_sweep():
    """Run every rate REPEATS times and write one CSV row per run.

    Returns the path of the CSV file it wrote.
    """
    if not CLIENT.exists():
        sys.exit("./client not found. Build it first (see README).")

    RESULTS_DIR.mkdir(exist_ok=True)
    csv_path = RESULTS_DIR / f"sweep-{time.strftime('%Y-%m-%d-%H%M')}.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()

        for rate in RATES:
            for run in range(1, REPEATS + 1):
                row = run_client(rate)
                if row["received"] == "0" and rate == RATES[0] and run == 1:
                    sys.exit("no replies at all. Is ./echo_server running?")

                row["run"] = run
                writer.writerow(row)
                f.flush()

                print(f"{rate:>7} pps  run {run}:  achieved {row['achieved_pps']:>7}"
                      f"  loss {float(row['loss_pct']):6.2f}%"
                      f"  p50 {row['p50_us']:>9}  p95 {row['p95_us']:>9}"
                      f"  p99 {row['p99_us']:>9} us")
                time.sleep(PAUSE_S)

    print(f"wrote {csv_path.relative_to(ROOT)}")
    return csv_path


def latest_csv():
    """The most recent sweep's CSV. The timestamped names sort by time."""
    found = sorted(RESULTS_DIR.glob("sweep-*.csv"))
    if not found:
        sys.exit("no sweep CSV in results/. Run python3 sweep.py first.")
    return found[-1]


def load_rows(csv_path):
    """Read the CSV back, turning every value into a number (or None if empty)."""
    with open(csv_path, newline="") as f:
        return [{key: float(value) if value else None for key, value in row.items()}
                for row in csv.DictReader(f)]


def median_by_rate(rows, column):
    """One point per target rate: the median of its runs, for x and for y."""
    points = []
    for rate in sorted({row["target_pps"] for row in rows}):
        runs = [row for row in rows
                if row["target_pps"] == rate and row[column] is not None]
        if runs:
            points.append((statistics.median(row["achieved_pps"] for row in runs),
                           statistics.median(row[column] for row in runs)))
    return points


def format_rate(value, _position):
    return f"{value / 1000:g}k"


def format_latency(value, _position):
    return f"{value / 1000:g} ms" if value >= 1000 else f"{value:g} µs"


def plot(csv_path):
    """Draw latency percentiles (top) and loss (bottom) against the send rate.

    The plot is saved next to the CSV, with the same name but ending in .png.
    """
    rows = load_rows(csv_path)
    plot_path = csv_path.with_suffix(".png")

    surface, ink, muted, grid = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
    plt.rcParams.update({"font.size": 10, "text.color": ink,
                         "axes.labelcolor": muted, "xtick.color": muted,
                         "ytick.color": muted, "axes.edgecolor": grid})

    fig, (latency_ax, loss_ax) = plt.subplots(
        2, 1, sharex=True, figsize=(9, 6.5), facecolor=surface,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.12})

    # top panel: one line per percentile through the median of the runs,
    # with every individual run shown as a faint dot behind it
    for column, label, colour, marker in PERCENTILES:
        measured = [row for row in rows if row[column] is not None]
        latency_ax.scatter([row["achieved_pps"] for row in measured],
                           [row[column] for row in measured],
                           s=14, color=colour, alpha=0.3, linewidths=0)
        points = median_by_rate(rows, column)
        latency_ax.plot([x for x, _ in points], [y for _, y in points],
                        color=colour, linewidth=2, marker=marker, markersize=6,
                        markeredgecolor=surface, markeredgewidth=1, label=label)

    latency_ax.set_xscale("log")
    latency_ax.set_yscale("log")
    latency_ax.set_ylabel("Round-trip time")
    latency_ax.yaxis.set_major_formatter(FuncFormatter(format_latency))
    latency_ax.legend(frameon=False, loc="upper left", title="median of runs",
                      alignment="left")
    latency_ax.set_title("Netpulse rate sweep: UDP echo over loopback",
                         loc="left", fontsize=12, fontweight="bold", pad=12)

    # bottom panel: loss on its own axis rather than a second scale up top
    loss_ax.scatter([row["achieved_pps"] for row in rows],
                    [row["loss_pct"] for row in rows],
                    s=14, color=muted, alpha=0.3, linewidths=0)
    points = median_by_rate(rows, "loss_pct")
    loss_ax.plot([x for x, _ in points], [y for _, y in points],
                 color=muted, linewidth=2, marker="o", markersize=6,
                 markeredgecolor=surface, markeredgewidth=1)
    loss_ax.set_ylabel("Packets lost")
    loss_ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:g}%"))
    loss_ax.set_ylim(bottom=-0.5)
    loss_ax.set_xlabel("Achieved send rate (packets per second)")
    loss_ax.xaxis.set_major_formatter(FuncFormatter(format_rate))
    loss_ax.xaxis.set_minor_formatter(NullFormatter())

    for ax in (latency_ax, loss_ax):
        ax.set_facecolor(surface)
        ax.grid(True, which="major", color=grid, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.tick_params(length=0, which="both")
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)

    fig.savefig(plot_path, dpi=160, bbox_inches="tight", facecolor=surface)
    print(f"wrote {plot_path.relative_to(ROOT)}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--plot-only" in args:
        args.remove("--plot-only")
        plot(Path(args[0]).resolve() if args else latest_csv())
    else:
        plot(run_sweep())

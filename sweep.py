#!/usr/bin/env python3
"""Rate sweep (Phase 3) with jitter and a written report (Phase 4).

Runs ./client at each rate in RATES, several times, and records every run.
Then plots latency percentiles, jitter and loss against the send rate, and
writes a report of the findings.

Every sweep gets its own folder, named after the date and time it started, so
earlier sweeps are never overwritten:

    results/2026-10-15-2130/
        sweep.csv    one row per run
        sweep.png    the plot
        report.md    the written findings
        meta.json    when, where and how the sweep was run

The echo server must already be running:     ./echo_server
Run the sweep:                               python3 sweep.py
Redraw plot and report of the latest sweep:  python3 sweep.py --redraw
Redraw plot and report of a chosen sweep:    python3 sweep.py --redraw results/2026-10-15-2130
"""

import csv
import json
import subprocess
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # draw straight to a file, no window needed
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, NullFormatter

from report import summarise, write_report

ROOT = Path(__file__).resolve().parent
CLIENT = ROOT / "client"
RESULTS_DIR = ROOT / "results"

# Send rates in packets per second. Spaced widely where the path is healthy,
# densely from 60,000 to 110,000 where earlier sweeps found the knee, and one
# rate far above the sender's ceiling to show where that ceiling is.
RATES = [1_000, 2_000, 5_000, 10_000, 20_000, 50_000,
         60_000, 70_000, 80_000, 85_000, 90_000, 95_000,
         100_000, 105_000, 110_000, 120_000, 200_000]

DURATION_S = 2   # how long each run sends for
REPEATS = 5      # runs per rate; near the knee runs disagree, so more of them helps
PAUSE_S = 1      # rest between runs so one run's queue does not leak into the next

# Column order of the line that `./client --csv` prints
CLIENT_FIELDS = ["target_pps", "achieved_pps", "sent", "received", "lost",
                 "loss_pct", "p50_us", "p95_us", "p99_us",
                 "jitter_rfc_us", "jitter_mean_us", "max_loss_burst"]
CSV_FIELDS = ["run"] + CLIENT_FIELDS

PERCENTILES = [  # column, label, colour, marker
    ("p50_us", "p50", "#2a78d6", "o"),
    ("p95_us", "p95", "#eb6834", "s"),
    ("p99_us", "p99", "#1baf7a", "^"),
]


def command_output(*command):
    """Output of a shell command, or None if it fails. Used for the setup record."""
    try:
        return subprocess.run(command, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def machine_meta():
    """When, where and with which code the sweep runs, for the report."""
    commit = command_output("git", "-C", str(ROOT), "rev-parse", "--short", "HEAD")
    if commit and command_output("git", "-C", str(ROOT), "status", "--porcelain"):
        commit += " plus uncommitted changes"
    power = command_output("pmset", "-g", "batt") or ""
    return {
        "started": time.strftime("%Y-%m-%d %H:%M"),
        "duration_s": DURATION_S,
        "repeats": REPEATS,
        "pause_s": PAUSE_S,
        "rates": RATES,
        "commit": commit,
        "macos": command_output("sw_vers", "-productVersion"),
        "cpu": command_output("sysctl", "-n", "machdep.cpu.brand_string"),
        "cores": command_output("sysctl", "-n", "hw.ncpu"),
        "power": ("on battery" if "Battery Power" in power
                  else "on mains power" if "AC Power" in power else None),
    }


def run_client(rate):
    """Run the client once at this rate and return its result as a dict."""
    done = subprocess.run([str(CLIENT), str(rate), str(DURATION_S), "--csv"],
                          capture_output=True, text=True)
    values = done.stdout.strip().split(",")
    if len(values) != len(CLIENT_FIELDS):
        sys.exit(f"unexpected output from client: {done.stdout!r} {done.stderr!r}\n"
                 "If ./client is an old build, rebuild it (see README).")
    return dict(zip(CLIENT_FIELDS, values))


def run_sweep():
    """Run every rate REPEATS times and write one CSV row per run.

    Returns the sweep's folder.
    """
    if not CLIENT.exists():
        sys.exit("./client not found. Build it first (see README).")

    meta = machine_meta()
    folder = RESULTS_DIR / time.strftime("%Y-%m-%d-%H%M")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    with open(folder / "sweep.csv", "w", newline="") as f:
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
                      f"  p50 {row['p50_us']:>9}  p99 {row['p99_us']:>9} us"
                      f"  jitter {row['jitter_mean_us']:>6} us")
                time.sleep(PAUSE_S)

    print(f"wrote {(folder / 'sweep.csv').relative_to(ROOT)}")
    return folder


def latest_folder():
    """The most recent sweep's folder. The dated names sort by time."""
    found = sorted(path.parent for path in RESULTS_DIR.glob("*/sweep.csv"))
    if not found:
        sys.exit("no sweep in results/. Run python3 sweep.py first.")
    return found[-1]


def load_rows(folder):
    """Read the CSV back, turning every value into a number (or None if empty).

    Sweeps from before Phase 4 have no jitter columns; those read as None.
    """
    with open(folder / "sweep.csv", newline="") as f:
        rows = [{key: float(value) if value else None for key, value in row.items()}
                for row in csv.DictReader(f)]
    for row in rows:
        for field in CSV_FIELDS:
            row.setdefault(field, None)
    return rows


def load_meta(folder):
    path = folder / "meta.json"
    return json.loads(path.read_text()) if path.exists() else {}


def format_rate(value, _position):
    return f"{value / 1000:g}k"


def format_us(value, _position):
    return f"{value / 1000:g} ms" if value >= 1000 else f"{value:g} µs"


def plot(folder, rows):
    """Draw latency percentiles, jitter and loss against the achieved send rate."""
    summary = summarise(rows)

    surface, ink, muted, grid = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
    plt.rcParams.update({"font.size": 10, "text.color": ink,
                         "axes.labelcolor": muted, "xtick.color": muted,
                         "ytick.color": muted, "axes.edgecolor": grid})

    # Sweeps from before Phase 4 have no jitter, so they get no jitter panel
    has_jitter = any(row["jitter_mean_us"] is not None for row in rows)
    if has_jitter:
        fig, (latency_ax, jitter_ax, loss_ax) = plt.subplots(
            3, 1, sharex=True, figsize=(9, 8.5), facecolor=surface,
            gridspec_kw={"height_ratios": [3, 1.4, 1], "hspace": 0.14})
        axes = (latency_ax, jitter_ax, loss_ax)
    else:
        fig, (latency_ax, loss_ax) = plt.subplots(
            2, 1, sharex=True, figsize=(9, 6.5), facecolor=surface,
            gridspec_kw={"height_ratios": [3, 1], "hspace": 0.12})
        axes = (latency_ax, loss_ax)

    def median_line(ax, column, colour, marker, label=None):
        """Faint dot per run, plus a line through the median of each rate."""
        measured = [row for row in rows if row[column] is not None]
        ax.scatter([row["achieved_pps"] for row in measured],
                   [row[column] for row in measured],
                   s=14, color=colour, alpha=0.3, linewidths=0)
        points = [p for p in summary if p[column] is not None]
        ax.plot([p["achieved_pps"] for p in points], [p[column] for p in points],
                color=colour, linewidth=2, marker=marker, markersize=6,
                markeredgecolor=surface, markeredgewidth=1, label=label)
        return bool(points)

    # Top panel: one line per percentile
    for column, label, colour, marker in PERCENTILES:
        median_line(latency_ax, column, colour, marker, label)
    latency_ax.set_xscale("log")
    latency_ax.set_yscale("log")
    latency_ax.set_ylabel("Round-trip time")
    latency_ax.yaxis.set_major_formatter(FuncFormatter(format_us))
    latency_ax.legend(frameon=False, loc="upper left", title="median of runs",
                      alignment="left")
    started = load_meta(folder).get("started", folder.name)
    latency_ax.set_title(f"Netpulse rate sweep: UDP echo over loopback, {started}",
                         loc="left", fontsize=12, fontweight="bold", pad=12)

    # Middle panel: jitter, on its own axis rather than a second scale up top
    if has_jitter:
        median_line(jitter_ax, "jitter_mean_us", muted, "o")
        jitter_ax.set_ylim(bottom=0)
        jitter_ax.yaxis.set_major_formatter(FuncFormatter(format_us))
        jitter_ax.set_ylabel("Jitter\n(mean change)")

    # Bottom panel: loss
    median_line(loss_ax, "loss_pct", muted, "o")
    loss_ax.set_ylabel("Packets lost")
    loss_ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:g}%"))
    loss_ax.set_ylim(bottom=-0.5)
    loss_ax.set_xlabel("Achieved send rate (packets per second)")
    loss_ax.xaxis.set_major_formatter(FuncFormatter(format_rate))
    loss_ax.xaxis.set_minor_formatter(NullFormatter())

    for ax in axes:
        ax.set_facecolor(surface)
        ax.grid(True, which="major", color=grid, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.tick_params(length=0, which="both")
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)

    fig.savefig(folder / "sweep.png", dpi=160, bbox_inches="tight", facecolor=surface)
    plt.close(fig)
    print(f"wrote {(folder / 'sweep.png').relative_to(ROOT)}")


def finish(folder):
    """Draw the plot and write the report for a sweep folder."""
    rows = load_rows(folder)
    plot(folder, rows)
    write_report(folder, rows, load_meta(folder))
    print(f"wrote {(folder / 'report.md').relative_to(ROOT)}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--redraw" in args:
        args.remove("--redraw")
        finish(Path(args[0]).resolve() if args else latest_folder())
    else:
        finish(run_sweep())

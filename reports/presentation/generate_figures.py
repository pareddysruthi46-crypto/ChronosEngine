from pathlib import Path
import csv
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = Path(__file__).resolve().parent
OUT.mkdir(parents=True, exist_ok=True)

# Verified matching-engine benchmark results
throughput = [346576, 475249, 448033, 530009, 501188,
              486299, 518928, 431419, 384590, 409477]
avg_throughput = 445490

# Verified matching latency percentiles and maximum, in microseconds
latency_labels = ["P50", "P90", "P99", "Maximum"]
latency_values = [1.2, 1.5, 3.2, 609.2]

# Actual ingestion benchmark results
batch_sizes = [100, 500, 1000]
persistence_rates = [7318, 21170, 22457]
drain_times = [6.0389, 1.2871, 0.6753]
backlogs = [43500, 25428, 17957]

plt.rcParams.update({
    "font.size": 11,
    "axes.titlesize": 17,
    "axes.labelsize": 12,
    "figure.facecolor": "white",
    "axes.facecolor": "#f7f9fc",
    "savefig.facecolor": "white",
})

def finish(fig, filename):
    fig.tight_layout()
    fig.savefig(OUT / filename, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print("Created:", filename)

# 1. Matching throughput across ten measured runs
fig, ax = plt.subplots(figsize=(13.33, 7.5))
bars = ax.bar(range(1, 11), throughput)
ax.axhline(avg_throughput, linestyle="--", linewidth=2,
           label=f"Average: {avg_throughput:,} orders/sec")
ax.set_title("ChronosEngine Matching Throughput")
ax.set_xlabel("Measured run")
ax.set_ylabel("Orders per second")
ax.set_xticks(range(1, 11))
ax.set_ylim(0, 600000)
ax.grid(axis="y", alpha=0.25)
ax.legend()
for bar, value in zip(bars, throughput):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 7000,
            f"{value/1000:.0f}k", ha="center", fontsize=9)
finish(fig, "matching_throughput.png")

# 2. Latency percentiles, with maximum retained to show the outlier
fig, ax = plt.subplots(figsize=(13.33, 7.5))
bars = ax.bar(latency_labels, latency_values)
ax.axhline(50, color="red", linestyle="--", linewidth=2,
           label="50 µs target threshold")
ax.set_yscale("log")
ax.set_title("Matching Latency: Percentiles and Maximum")
ax.set_ylabel("Latency (microseconds, logarithmic scale)")
ax.grid(axis="y", alpha=0.25, which="both")
ax.legend()
for bar, value in zip(bars, latency_values):
    ax.text(bar.get_x() + bar.get_width()/2, value * 1.15,
            f"{value:,.1f} µs", ha="center", fontsize=10)
ax.text(0.02, 0.96, "99.962% of measured operations were below 50 µs",
        transform=ax.transAxes, va="top", fontsize=12)
finish(fig, "matching_latency.png")

# 3. Persistence rate by batch size
fig, ax = plt.subplots(figsize=(13.33, 7.5))
bars = ax.bar([str(x) for x in batch_sizes], persistence_rates)
ax.set_title("Trade Ledger Ingestion: Persistence Rate by Batch Size")
ax.set_xlabel("Consumer batch size")
ax.set_ylabel("End-to-end persisted trades per second")
ax.grid(axis="y", alpha=0.25)
for bar, value in zip(bars, persistence_rates):
    ax.text(bar.get_x() + bar.get_width()/2, value + 500,
            f"{value:,}/sec", ha="center", fontsize=11)
ax.text(0.02, 0.96, "50,000 submitted and persisted; zero missing in each run",
        transform=ax.transAxes, va="top", fontsize=11)
finish(fig, "ingestion_persistence_rate.png")

# 4. Queue drain time and sampled backlog
fig, ax1 = plt.subplots(figsize=(13.33, 7.5))
x = range(len(batch_sizes))
bars = ax1.bar([i - 0.18 for i in x], drain_times, width=0.36,
               label="Queue drain time (sec)")
ax1.set_xticks(list(x))
ax1.set_xticklabels([str(x) for x in batch_sizes])
ax1.set_xlabel("Consumer batch size")
ax1.set_ylabel("Queue drain time (seconds)")
ax1.set_title("Ingestion Queue Drain and Sampled Backlog")
ax1.grid(axis="y", alpha=0.25)
for bar, value in zip(bars, drain_times):
    ax1.text(bar.get_x() + bar.get_width()/2, value + 0.12,
             f"{value:.2f}s", ha="center", fontsize=9)

ax2 = ax1.twinx()
ax2.plot(list(x), backlogs, marker="o", linewidth=2,
         label="Maximum sampled backlog")
ax2.set_ylabel("Maximum sampled backlog (trades)")
for i, value in enumerate(backlogs):
    ax2.annotate(f"{value:,}", (i, value), xytext=(0, 10),
                 textcoords="offset points", ha="center", fontsize=9)

h1, l1 = ax1.get_legend_handles_labels()
h2, l2 = ax2.get_legend_handles_labels()
ax1.legend(h1 + h2, l1 + l2, loc="upper right")
finish(fig, "ingestion_queue_metrics.png")

# 5. Pipeline flow diagram.
# This depicts the async trade-ledger path: trade publication enters
# a multiprocessing queue, then a batch consumer writes to SQLite.
fig, ax = plt.subplots(figsize=(16, 6))
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")
ax.set_title("ChronosEngine: Matching and Asynchronous Persistence Pipeline",
             fontsize=19, pad=20)

nodes = [
    ("Order\nproducer", "Creates incoming orders"),
    ("Order mmap\nring buffer", "Shared-memory IPC"),
    ("Order consumer /\nmatching engine", "Matches orders"),
    ("Trade\npublisher", "Publishes new fills"),
    ("Multiprocessing\nqueue", "Buffers trade records"),
    ("Batch consumer\nworker", "Batches and retries writes"),
    ("SQLite WAL\ntrade ledger", "Persists indexed trades"),
]

left = 0.025
width = 0.122
gap = 0.021
y = 0.43
height = 0.32

for i, (title, subtitle) in enumerate(nodes):
    x = left + i * (width + gap)
    box = FancyBboxPatch(
        (x, y), width, height,
        boxstyle="round,pad=0.012,rounding_size=0.02",
        linewidth=1.5, edgecolor="#315b85", facecolor="#eaf2fb"
    )
    ax.add_patch(box)
    ax.text(x + width/2, y + 0.205, title, ha="center", va="center",
            fontsize=10, fontweight="bold")
    ax.text(x + width/2, y + 0.075, subtitle, ha="center", va="center",
            fontsize=8, wrap=True)
    if i < len(nodes) - 1:
        start = (x + width + 0.002, y + height/2)
        end = (x + width + gap - 0.002, y + height/2)
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>",
                                     mutation_scale=13, linewidth=1.5,
                                     color="#52677d"))

ax.text(0.5, 0.20,
        "Decoupled persistence: matching publishes trades; the worker batches writes "
        "to the durable ledger.",
        ha="center", fontsize=11)
ax.text(0.5, 0.10,
        "SQLite configuration: WAL journal mode; synchronous=FULL",
        ha="center", fontsize=10)
finish(fig, "pipeline_flow.png")

# Machine-readable summary
with (OUT / "benchmark_summary.csv").open("w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["benchmark", "configuration", "metric", "value", "unit"])
    for i, value in enumerate(throughput, 1):
        writer.writerow(["matching", f"run_{i}", "throughput", value, "orders/sec"])
    writer.writerow(["matching", "10_runs", "average_throughput",
                     avg_throughput, "orders/sec"])
    for label, value in zip(latency_labels, latency_values):
        writer.writerow(["matching_latency", "aggregate", label, value, "microseconds"])
    for batch, rate, drain, backlog in zip(
            batch_sizes, persistence_rates, drain_times, backlogs):
        writer.writerow(["ingestion", f"batch_{batch}",
                         "end_to_end_persistence_rate", rate, "trades/sec"])
        writer.writerow(["ingestion", f"batch_{batch}",
                         "queue_drain_time", drain, "seconds"])
        writer.writerow(["ingestion", f"batch_{batch}",
                         "maximum_sampled_backlog", backlog, "trades"])

print("Created: benchmark_summary.csv")
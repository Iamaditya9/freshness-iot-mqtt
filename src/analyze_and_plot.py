import argparse
import os
import pandas as pd
import matplotlib.pyplot as plt


def generate_summary_and_plots(csv_path: str):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Could not find {csv_path}. Run run_experiments.py first.")

    df = pd.read_csv(csv_path)
    os.makedirs("results/plots", exist_ok=True)

    # 1. Aggregated summary table across repetitions
    summary = (
        df.groupby(["outage_sec", "rate_hz", "strategy"], as_index=False)
        .agg(
            runs=("rep", "count"),
            median_aoi_sec=("median_aoi_sec", "mean"),
            p95_aoi_sec=("p95_aoi_sec", "mean"),
            mean_recovery_sec=("mean_recovery_sec", "mean"),
            delivery_ratio=("delivery_ratio", "mean"),
            median_delay_sec=("median_delay_sec", "mean"),
            dropped_overflow=("dropped_overflow", "mean"),
            dropped_stale=("dropped_stale", "mean"),
            tx_bytes=("tx_bytes", "mean"),
        )
        .round(4)
    )

    summary_path = "results/summary_table.csv"
    summary.to_csv(summary_path, index=False)
    print(f"Saved summary table to {summary_path}\n")
    print(summary.to_string(index=False))

    # Helper for grouped bar/line plots by outage duration (averaged or faceted by rate)
    rates = sorted(summary["rate_hz"].unique())

    # Plot 1: 95th-Percentile Age of Information (AoI) vs Outage Duration
    fig, axes = plt.subplots(1, len(rates), figsize=(5 * len(rates), 4.5), sharey=True)
    if len(rates) == 1:
        axes = [axes]
    for ax, rate in zip(axes, rates):
        sub = summary[summary["rate_hz"] == rate]
        for strat, marker in [("fifo", "o"), ("freshness", "s")]:
            s = sub[sub["strategy"] == strat]
            ax.plot(s["outage_sec"], s["p95_aoi_sec"], marker=marker, linewidth=2, label=strat.upper())
        ax.set_title(f"Rate = {rate} msg/s")
        ax.set_xlabel("Outage Duration (s)")
        ax.grid(True, linestyle="--", alpha=0.5)
        ax.legend()
    axes[0].set_ylabel("95th-Percentile AoI (s)")
    fig.suptitle("Message Freshness (95th-Percentile AoI): FIFO vs Freshness-Aware", fontsize=13)
    plt.tight_layout()
    plt.savefig("results/plots/p95_aoi_comparison.png", dpi=300)
    plt.close()

    # Plot 2: Recovery Time vs Outage Duration
    fig, axes = plt.subplots(1, len(rates), figsize=(5 * len(rates), 4.5), sharey=True)
    if len(rates) == 1:
        axes = [axes]
    for ax, rate in zip(axes, rates):
        sub = summary[summary["rate_hz"] == rate]
        for strat, marker in [("fifo", "o"), ("freshness", "s")]:
            s = sub[sub["strategy"] == strat]
            ax.plot(s["outage_sec"], s["mean_recovery_sec"], marker=marker, linewidth=2, label=strat.upper())
        ax.set_title(f"Rate = {rate} msg/s")
        ax.set_xlabel("Outage Duration (s)")
        ax.grid(True, linestyle="--", alpha=0.5)
        ax.legend()
    axes[0].set_ylabel("Mean Recovery Time (s)")
    fig.suptitle("Post-Outage Recovery Time: FIFO vs Freshness-Aware", fontsize=13)
    plt.tight_layout()
    plt.savefig("results/plots/recovery_time_comparison.png", dpi=300)
    plt.close()

    # Plot 3: Delivery Ratio Trade-off
    fig, axes = plt.subplots(1, len(rates), figsize=(5 * len(rates), 4.5), sharey=True)
    if len(rates) == 1:
        axes = [axes]
    for ax, rate in zip(axes, rates):
        sub = summary[summary["rate_hz"] == rate]
        for strat, marker in [("fifo", "o"), ("freshness", "s")]:
            s = sub[sub["strategy"] == strat]
            ax.plot(s["outage_sec"], s["delivery_ratio"], marker=marker, linewidth=2, label=strat.upper())
        ax.set_title(f"Rate = {rate} msg/s")
        ax.set_xlabel("Outage Duration (s)")
        ax.set_ylim(0, 1.08)
        ax.grid(True, linestyle="--", alpha=0.5)
        ax.legend()
    axes[0].set_ylabel("Delivery Ratio (Unique Rx / Generated)")
    fig.suptitle("Historical Delivery Ratio Trade-Off: FIFO vs Freshness-Aware", fontsize=13)
    plt.tight_layout()
    plt.savefig("results/plots/delivery_ratio_comparison.png", dpi=300)
    plt.close()

    # Plot 4: Communication Overhead (Transmitted Bytes)
    fig, axes = plt.subplots(1, len(rates), figsize=(5 * len(rates), 4.5), sharey=True)
    if len(rates) == 1:
        axes = [axes]
    for ax, rate in zip(axes, rates):
        sub = summary[summary["rate_hz"] == rate]
        for strat, marker in [("fifo", "o"), ("freshness", "s")]:
            s = sub[sub["strategy"] == strat]
            ax.plot(s["outage_sec"], s["tx_bytes"] / 1024.0, marker=marker, linewidth=2, label=strat.upper())
        ax.set_title(f"Rate = {rate} msg/s")
        ax.set_xlabel("Outage Duration (s)")
        ax.grid(True, linestyle="--", alpha=0.5)
        ax.legend()
    axes[0].set_ylabel("Transmitted Payload (KB)")
    fig.suptitle("Communication Overhead: FIFO vs Freshness-Aware", fontsize=13)
    plt.tight_layout()
    plt.savefig("results/plots/overhead_comparison.png", dpi=300)
    plt.close()

    print("\nSaved 4 plots to results/plots/:")
    print(" - p95_aoi_comparison.png")
    print(" - recovery_time_comparison.png")
    print(" - delivery_ratio_comparison.png")
    print(" - overhead_comparison.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--csv",
        default="results/raw/experiment_results.csv",
        help="Path to raw experiment CSV",
    )
    args = parser.parse_args()
    generate_summary_and_plots(args.csv)
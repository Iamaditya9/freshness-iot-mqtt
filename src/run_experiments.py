import argparse
import os
import threading
import time
import pandas as pd

from config import (
    OUTAGE_DURATIONS_SEC,
    MESSAGE_RATES_HZ,
    REPETITIONS,
    PRE_OUTAGE_SEC,
    POST_OUTAGE_SEC,
    RunConfig,
)
from publisher import SensorSimulator
from subscriber import TelemetrySubscriber


def execute_single_run(cfg: RunConfig) -> dict:
    outage_flag = threading.Event()
    sub = TelemetrySubscriber(num_sensors=cfg.num_sensors, qos=cfg.qos)
    sub.start()

    sensors = [
        SensorSimulator(f"sensor_{i}", cfg, outage_flag)
        for i in range(cfg.num_sensors)
    ]

    total_duration = PRE_OUTAGE_SEC + cfg.outage_sec + POST_OUTAGE_SEC
    threads = [
        threading.Thread(target=s.run_for_schedule, args=(total_duration,))
        for s in sensors
    ]

    for t in threads:
        t.start()

    # Phase 1: Stable pre-outage
    time.sleep(PRE_OUTAGE_SEC)

    # Phase 2: Controlled outage
    outage_flag.set()
    time.sleep(cfg.outage_sec)

    # Phase 3: Reconnection & recovery
    outage_end_ts = time.time()
    outage_flag.clear()

    for t in threads:
        t.join()

    time.sleep(0.5)  # Allow final in-flight MQTT packets to arrive
    sub.stop()

    # Aggregate metrics
    pub_stats = [s.summary() for s in sensors]
    total_gen = sum(p["generated"] for p in pub_stats)
    total_pub = sum(p["published"] for p in pub_stats)
    total_tx_bytes = sum(p["tx_bytes"] for p in pub_stats)
    dropped_overflow = sum(p["dropped_overflow"] for p in pub_stats)
    dropped_stale = sum(p["dropped_stale"] for p in pub_stats)

    unique_rx = sum(len(seqs) for seqs in sub.seen_seqs.values())
    delivery_ratio = unique_rx / total_gen if total_gen > 0 else 0.0

    aoi_df = pd.DataFrame(sub.aoi_samples)
    median_aoi = float(aoi_df["aoi_sec"].median()) if not aoi_df.empty else 0.0
    p95_aoi = float(aoi_df["aoi_sec"].quantile(0.95)) if not aoi_df.empty else 0.0

    rx_df = pd.DataFrame(sub.received_records)
    median_delay = float(rx_df["e2e_delay"].median()) if not rx_df.empty else 0.0
    p95_delay = float(rx_df["e2e_delay"].quantile(0.95)) if not rx_df.empty else 0.0

    rec_times = sub.compute_recovery_times(outage_end_ts)
    mean_recovery = (
        sum(rec_times.values()) / len(rec_times) if rec_times else float("nan")
    )

    return {
        "strategy": cfg.strategy,
        "outage_sec": cfg.outage_sec,
        "rate_hz": cfg.rate_hz,
        "rep": cfg.rep,
        "total_generated": total_gen,
        "total_published": total_pub,
        "unique_received": unique_rx,
        "duplicates": sub.duplicate_count,
        "dropped_overflow": dropped_overflow,
        "dropped_stale": dropped_stale,
        "delivery_ratio": round(delivery_ratio, 4),
        "median_aoi_sec": round(median_aoi, 4),
        "p95_aoi_sec": round(p95_aoi, 4),
        "median_delay_sec": round(median_delay, 4),
        "p95_delay_sec": round(p95_delay, 4),
        "mean_recovery_sec": round(mean_recovery, 4),
        "tx_bytes": total_tx_bytes,
        "rx_bytes": sub.total_rx_bytes,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true", help="Run a quick 2-run pilot test")
    args = parser.parse_args()

    os.makedirs("results/raw", exist_ok=True)
    results = []

    if args.pilot:
        configs = [
            RunConfig(strategy="fifo", outage_sec=5, rate_hz=5, rep=1),
            RunConfig(strategy="freshness", outage_sec=5, rate_hz=5, rep=1),
        ]
        out_path = "results/raw/pilot_results.csv"
    else:
        configs = [
            RunConfig(strategy=strat, outage_sec=outage, rate_hz=rate, rep=rep)
            for outage in OUTAGE_DURATIONS_SEC
            for rate in MESSAGE_RATES_HZ
            for strat in ["fifo", "freshness"]
            for rep in range(1, REPETITIONS + 1)
        ]
        out_path = "results/raw/experiment_results.csv"

    print(f"Starting {len(configs)} experiment run(s)...")
    for idx, cfg in enumerate(configs, start=1):
        print(
            f"[{idx}/{len(configs)}] strategy={cfg.strategy} | "
            f"outage={cfg.outage_sec}s | rate={cfg.rate_hz}Hz | rep={cfg.rep}"
        )
        row = execute_single_run(cfg)
        results.append(row)
        print(
            f"   -> AoI(med/p95): {row['median_aoi_sec']}s / {row['p95_aoi_sec']}s | "
            f"Recovery: {row['mean_recovery_sec']}s | Delivery: {row['delivery_ratio']}"
        )
        # Save incrementally so no data is lost if interrupted
        pd.DataFrame(results).to_csv(out_path, index=False)

    print(f"\nDone! Results saved to {out_path}")


if __name__ == "__main__":
    main()
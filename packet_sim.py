"""
Packet Size Optimization Simulator  (Phase 2 + Phase 3 starter)
----------------------------------------------------------------
Model : Sender --(link: bandwidth, propagation delay, BER)--> Receiver
Proto : Stop-and-Wait ARQ with timeout + retransmission
Goal  : Study how payload (packet) size affects throughput, goodput, latency.

Run   : python packet_sim.py
Needs : pip install matplotlib numpy pandas
Output: results/per_packet_log.csv, results/summary.csv, results/*.png
"""
import math
import os
import random
from dataclasses import dataclass

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# ----------------------------------------------------------------------
# Phase 2: core simulator
# ----------------------------------------------------------------------
@dataclass
class LinkConfig:
    bandwidth_bps: float = 10e6      # 10 Mbps
    prop_delay_s: float = 0.010      # 10 ms one-way
    ber: float = 0.0                 # bit error rate
    header_bytes: int = 40           # TCP/IP-like header
    ack_bytes: int = 40              # ACK packet size
    timeout_margin_s: float = 0.005  # added on top of ideal RTT
    max_retries: int = 100           # give up on a packet after this many tries


def packet_error_prob(size_bytes: int, ber: float) -> float:
    """P(at least one bit error) = 1 - (1 - BER)^bits."""
    if ber <= 0:
        return 0.0
    return 1.0 - (1.0 - ber) ** (8 * size_bytes)


def simulate_transfer(total_bytes, payload_bytes, cfg: LinkConfig, rng, log=None, tag=None):
    """
    Send `total_bytes` of application data using packets of `payload_bytes`.
    Returns a dict of metrics. If `log` (list) is given, per-packet rows are appended.
    """
    n_packets = math.ceil(total_bytes / payload_bytes)
    clock = 0.0
    delivered_payload = 0
    wire_bytes_ok = 0          # bytes of successfully ACKed frames (payload + header)
    total_tx = 0               # total transmissions (incl. retransmissions)
    failed_packets = 0
    latencies = []

    ack_tx_time = cfg.ack_bytes * 8 / cfg.bandwidth_bps
    p_ack_err = packet_error_prob(cfg.ack_bytes, cfg.ber)

    for seq in range(n_packets):
        this_payload = min(payload_bytes, total_bytes - seq * payload_bytes)
        frame = this_payload + cfg.header_bytes
        tx_time = frame * 8 / cfg.bandwidth_bps
        p_err = packet_error_prob(frame, cfg.ber)
        ideal_rtt = tx_time + 2 * cfg.prop_delay_s + ack_tx_time
        timeout = ideal_rtt + cfg.timeout_margin_s

        t_first_send = clock
        attempts = 0
        success = False
        while attempts < cfg.max_retries:
            attempts += 1
            total_tx += 1
            data_ok = rng.random() >= p_err
            ack_ok = data_ok and (rng.random() >= p_ack_err)
            if ack_ok:
                clock += ideal_rtt          # data + ACK come back
                success = True
                break
            clock += timeout                # wait for timeout then resend

        latency = clock - t_first_send
        if success:
            delivered_payload += this_payload
            wire_bytes_ok += frame
            latencies.append(latency)
        else:
            failed_packets += 1

        if log is not None:
            log.append({**(tag or {}), "seq": seq, "payload": this_payload,
                        "attempts": attempts, "success": success,
                        "start_s": t_first_send, "end_s": clock,
                        "latency_s": latency})

    total_time = clock if clock > 0 else 1e-12
    return {
        "packets": n_packets,
        "total_time_s": total_time,
        "throughput_mbps": wire_bytes_ok * 8 / total_time / 1e6,
        "goodput_mbps": delivered_payload * 8 / total_time / 1e6,
        "avg_latency_ms": 1000 * np.mean(latencies) if latencies else float("nan"),
        "p95_latency_ms": 1000 * np.percentile(latencies, 95) if latencies else float("nan"),
        "retx_per_packet": (total_tx - n_packets) / n_packets,
        "loss_pct": 100 * failed_packets / n_packets,
        "efficiency": payload_bytes / (payload_bytes + cfg.header_bytes),
    }


# ----------------------------------------------------------------------
# Phase 3: experiments
# ----------------------------------------------------------------------
PACKET_SIZES = [64, 128, 256, 512, 1024, 1500, 2048, 4096, 8192]
BER_VALUES = [0.0, 1e-6, 1e-5, 5e-5, 1e-4]
TOTAL_BYTES = 500_000
TRIALS = 20
OUT = "results"


def run_sweep(ber_values, sizes, trials=TRIALS, seed=42, log=None):
    rows = []
    for ber in ber_values:
        cfg = LinkConfig(ber=ber)
        for size in sizes:
            runs = []
            for t in range(trials):
                rng = random.Random(seed + 1000 * t + size)
                # log only the first trial to keep the CSV small
                lg = log if (log is not None and t == 0) else None
                runs.append(simulate_transfer(TOTAL_BYTES, size, cfg, rng, lg,
                                              {"ber": ber, "size": size}))
            df = pd.DataFrame(runs)
            row = {"ber": ber, "packet_size": size}
            for col in ["throughput_mbps", "goodput_mbps", "avg_latency_ms",
                        "p95_latency_ms", "retx_per_packet", "loss_pct", "efficiency"]:
                row[col + "_mean"] = df[col].mean()
                row[col + "_std"] = df[col].std(ddof=1)
            rows.append(row)
    return pd.DataFrame(rows)


def plot_metric(summary, metric, ylabel, title, fname, bers=None, logx=True):
    plt.figure(figsize=(7, 4.5))
    for ber in (bers if bers is not None else sorted(summary.ber.unique())):
        d = summary[summary.ber == ber]
        plt.errorbar(d.packet_size, d[metric + "_mean"], yerr=d[metric + "_std"],
                     marker="o", capsize=3, label=f"BER={ber:g}")
        if metric == "goodput_mbps":     # mark the optimum
            best = d.loc[d[metric + "_mean"].idxmax()]
            plt.scatter([best.packet_size], [best[metric + "_mean"]],
                        s=130, facecolors="none", edgecolors="k")
    if logx:
        plt.xscale("log", base=2)
    plt.xlabel("Payload size (bytes)")
    plt.ylabel(ylabel)
    plt.title(title)
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(OUT, fname), dpi=150)
    plt.close()


def main():
    os.makedirs(OUT, exist_ok=True)

    # Experiment 1: baseline, clean link
    print("Experiment 1: baseline (BER=0)")
    pkt_log = []
    base = run_sweep([0.0], PACKET_SIZES, log=pkt_log)
    print(base[["packet_size", "throughput_mbps_mean", "goodput_mbps_mean",
                "avg_latency_ms_mean"]].round(3).to_string(index=False))

    # Experiment 2: noisy link, several BER values
    print("\nExperiment 2: noisy links")
    noisy = run_sweep(BER_VALUES, PACKET_SIZES, log=pkt_log)

    pd.DataFrame(pkt_log).to_csv(os.path.join(OUT, "per_packet_log.csv"), index=False)
    noisy.to_csv(os.path.join(OUT, "summary.csv"), index=False)

    # Optimal packet size per BER
    print("\nOptimal packet size (max goodput) per BER:")
    for ber in BER_VALUES:
        d = noisy[noisy.ber == ber]
        b = d.loc[d.goodput_mbps_mean.idxmax()]
        print(f"  BER={ber:<8g} -> {int(b.packet_size):>5} B  "
              f"(goodput {b.goodput_mbps_mean:.3f} Mbps)")

    # Graphs
    plot_metric(base, "throughput_mbps", "Throughput (Mbps)",
                "Throughput vs packet size (clean link)", "exp1_throughput.png")
    plot_metric(base, "avg_latency_ms", "Avg per-packet latency (ms)",
                "Latency vs packet size (clean link)", "exp1_latency.png")
    plot_metric(noisy, "goodput_mbps", "Goodput (Mbps)",
                "Goodput vs packet size under different BER", "exp2_goodput.png")
    plot_metric(noisy, "avg_latency_ms", "Avg per-packet latency (ms)",
                "Latency vs packet size under different BER", "exp2_latency.png")
    plot_metric(noisy, "retx_per_packet", "Retransmissions per packet",
                "Retransmissions vs packet size", "exp2_retx.png")
    print(f"\nSaved CSVs and graphs in ./{OUT}/")


if __name__ == "__main__":
    main()

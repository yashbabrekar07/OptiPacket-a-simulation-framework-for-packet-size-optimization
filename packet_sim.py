"""
Packet Size Optimization Simulator (Phases A through F Complete)
----------------------------------------------------------------
Model   : Sender --(Bottleneck Link Queue, Propagation Delay, BER)--> Receiver
Protocols:
  - Stop-and-Wait ARQ (baseline)
  - Go-Back-N Sliding Window (configurable window W, cumulative ACKs)
  - Selective Repeat Sliding Window (configurable window W, individual ACKs)
  - Dynamic Adaptive Packet Sizing (channel-aware online optimization)
Realism :
  - MTU enforcement (default 1500 B Ethernet frame)
  - IP/Link Fragmentation with reassembly failure penalty
  - Bottleneck Link Queue (finite FIFO buffer, tail drop on overflow)
  - Queuing delay tracking
  - Multi-flow contention support

Dependencies: numpy, pandas, matplotlib, scipy
"""
import math
import os
import random
import heapq
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# ----------------------------------------------------------------------
# 1. Configuration Dataclass
# ----------------------------------------------------------------------
@dataclass
class LinkConfig:
    bandwidth_bps: float = 10e6        # Bottleneck bandwidth (default 10 Mbps)
    prop_delay_s: float = 0.010        # One-way propagation delay (default 10 ms)
    ber: float = 0.0                   # Bit error rate (0.0 to 1e-3)
    header_bytes: int = 40             # Header size (TCP 20B + IPv4 20B = 40B; IPv6 = 60B)
    ack_bytes: int = 40                # ACK packet size
    timeout_margin_s: float = 0.005    # Timeout guard margin added to ideal RTT
    max_retries: int = 100             # Max attempts before giving up on a packet
    protocol: str = "stop_and_wait"    # "stop_and_wait", "go_back_n", "selective_repeat", "adaptive"
    window_size: int = 1               # Sliding window size W (used for GBN and SR)
    mtu_bytes: int = 1500              # Maximum Transmission Unit (default 1500 B Ethernet)
    enable_fragmentation: bool = True  # Enable fragmentation if frame > MTU
    queue_capacity: int = 50           # Max frames queued at bottleneck link (0 = infinite)
    n_flows: int = 1                   # Number of concurrent competing flows


# ----------------------------------------------------------------------
# 2. Probability and Theoretical Utilities
# ----------------------------------------------------------------------
def packet_error_prob(size_bytes: int, ber: float) -> float:
    """Calculates P(at least one bit error in frame) = 1 - (1 - BER)^(8 * size_bytes)."""
    if ber <= 0.0:
        return 0.0
    if ber >= 1.0:
        return 1.0
    return 1.0 - (1.0 - ber) ** (8 * size_bytes)


def calculate_theoretical_optimal(ber: float, header_bytes: int = 40,
                                   bandwidth_bps: float = 10e6,
                                   prop_delay_s: float = 0.010,
                                   ack_bytes: int = 40) -> float:
    """
    Computes theoretical optimal payload size L* maximizing expected goodput G(L).
    Accurately accounts for:
      - Packet transmission delay: (L + H) * 8 / R
      - Two-way propagation delay: 2 * Tp
      - ACK transmission delay: Hack * 8 / R
      - Geometric retransmissions: 1 / (1 - BER)^(8 * (L + H))
    Finds the global maximum over candidate byte sizes.
    """
    if ber <= 0.0:
        return 8192.0

    best_L = 64.0
    best_gp = -1.0
    # Fine-grained grid search for exact analytical maximum
    for L in range(32, 8193, 4):
        tx = (L + header_bytes) * 8.0 / bandwidth_bps
        ack_tx = ack_bytes * 8.0 / bandwidth_bps
        rtt = tx + 2.0 * prop_delay_s + ack_tx
        p_succ = (1.0 - ber) ** (8.0 * (L + header_bytes))
        expected_time = rtt / max(1e-15, p_succ)
        gp = (L * 8.0) / expected_time
        if gp > best_gp:
            best_gp = gp
            best_L = float(L)
    return best_L


# ----------------------------------------------------------------------
# 3. Core Discrete-Event Network Simulator
# ----------------------------------------------------------------------
def simulate_transfer(total_bytes: int, payload_bytes: int, cfg: LinkConfig,
                      rng: random.Random, log: Optional[List[Dict[str, Any]]] = None,
                      tag: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Simulates sending `total_bytes` of application data using the configured protocol.
    Accurately captures:
      - Sliding window pipelining (Stop-and-Wait, Go-Back-N, Selective Repeat, Adaptive)
      - MTU-based fragmentation and whole-packet retransmission on fragment corruption
      - Finite queue buffering, tail-drop overflow, and queuing delay
      - Multiple competing flows
    Returns comprehensive performance metrics and optionally appends per-packet logs.
    """
    proto = cfg.protocol.lower()
    window_size = 1 if proto == "stop_and_wait" else max(1, cfg.window_size)
    mtu = cfg.mtu_bytes
    header = cfg.header_bytes
    ack_bytes = cfg.ack_bytes
    bandwidth = cfg.bandwidth_bps
    prop_delay = cfg.prop_delay_s
    ber = cfg.ber
    ack_tx_time = ack_bytes * 8.0 / bandwidth
    p_ack_err = packet_error_prob(ack_bytes, ber)

    # Initial packet partition
    # For adaptive mode, payload size starts at payload_bytes and adapts dynamically
    is_adaptive = (proto == "adaptive")
    current_payload_size = payload_bytes if is_adaptive else payload_bytes

    def build_packet_meta(seq_idx: int, p_size: int, byte_offset: int, total_b: int) -> Dict[str, Any]:
        actual_payload = min(p_size, total_b - byte_offset)
        # Check MTU and fragmentation
        if cfg.enable_fragmentation and (actual_payload + header) > mtu:
            max_frag_payload = max(1, mtu - header)
            n_frags = math.ceil(actual_payload / max_frag_payload)
            frag_sizes = []
            rem = actual_payload
            for _ in range(n_frags):
                f_p = min(max_frag_payload, rem)
                frag_sizes.append(f_p + header)
                rem -= f_p
            wire_bytes = sum(frag_sizes)
            # Packet fails if ANY fragment suffers bit error
            p_err = 1.0 - (1.0 - ber) ** (8 * wire_bytes) if ber > 0 else 0.0
        else:
            wire_bytes = actual_payload + header
            n_frags = 1
            frag_sizes = [wire_bytes]
            p_err = packet_error_prob(wire_bytes, ber)

        tx_time = wire_bytes * 8.0 / bandwidth
        ideal_rtt = tx_time + 2.0 * prop_delay + ack_tx_time
        timeout = ideal_rtt + cfg.timeout_margin_s
        return {
            "seq": seq_idx,
            "payload": actual_payload,
            "wire_bytes": wire_bytes,
            "n_frags": n_frags,
            "frag_sizes": frag_sizes,
            "p_err": p_err,
            "tx_time": tx_time,
            "ideal_rtt": ideal_rtt,
            "timeout": timeout,
        }

    # Pre-build packet metadata or dynamically create for adaptive
    packets: List[Dict[str, Any]] = []
    if not is_adaptive:
        n_packets = math.ceil(total_bytes / payload_bytes)
        offset = 0
        for s in range(n_packets):
            pmeta = build_packet_meta(s, payload_bytes, offset, total_bytes)
            packets.append(pmeta)
            offset += pmeta["payload"]
    else:
        # Pre-allocate placeholder count (approximate)
        n_packets = math.ceil(total_bytes / payload_bytes)

    # Event Queue: entries are (timestamp, event_id, event_type, payload_dict)
    event_counter = 0
    event_queue: List[Tuple[float, int, str, Any]] = []

    def schedule_event(t: float, ev_type: str, data: Any):
        nonlocal event_counter
        heapq.heappush(event_queue, (t, event_counter, ev_type, data))
        event_counter += 1

    clock = 0.0
    link_busy_until = 0.0
    link_queue: List[Dict[str, Any]] = []  # Packets waiting for wire transmission
    queue_drops = 0
    queuing_delays: List[float] = []

    # Dynamic flow / sender state
    delivered_payload = 0
    total_wire_bytes_ok = 0
    total_transmissions = 0
    failed_packets = 0
    total_fragments_created = 0

    # Tracking arrays
    send_attempts: Dict[int, int] = {}
    first_send_time: Dict[int, float] = {}
    completion_time: Dict[int, float] = {}
    packet_success: Dict[int, bool] = {}
    current_attempt_id: Dict[int, int] = {}

    # Sliding Window state
    base = 0
    next_seq = 0
    expected_seq = 0       # Receiver state for Go-Back-N
    rcv_buffer = set()     # Receiver buffer for Selective Repeat
    base_timer_active = False
    base_timeout_time = 0.0

    # Adaptive state
    adaptive_window_attempts = 0
    adaptive_window_losses = 0
    adaptive_offset = 0

    def get_or_create_packet(seq_idx: int) -> Dict[str, Any]:
        nonlocal adaptive_offset, n_packets
        if seq_idx < len(packets):
            return packets[seq_idx]
        if is_adaptive and adaptive_offset < total_bytes:
            pmeta = build_packet_meta(seq_idx, current_payload_size, adaptive_offset, total_bytes)
            packets.append(pmeta)
            adaptive_offset += pmeta["payload"]
            n_packets = len(packets)
            return pmeta
        raise IndexError(f"Packet index {seq_idx} out of range")

    def service_link_queue(now: float):
        nonlocal link_busy_until
        if not link_queue or now < link_busy_until:
            return
        item = link_queue.pop(0)
        seq_i = item["seq"]
        p_info = packets[seq_i]
        q_wait = max(0.0, now - item["enqueued_at"])
        queuing_delays.append(q_wait)

        # Transmission on wire
        tx_time = p_info["tx_time"]
        link_busy_until = now + tx_time
        # Packet arrives at receiver after transmission finishes + propagation delay
        schedule_event(now + tx_time + prop_delay, "PKT_ARRIVE", {
            "seq": seq_i,
            "attempt_id": item["attempt_id"],
            "wire_bytes": p_info["wire_bytes"]
        })
        # Schedule wire free event
        schedule_event(link_busy_until, "LINK_FREE", None)

    def send_packet(seq_i: int, now: float):
        nonlocal queue_drops, total_transmissions, total_fragments_created
        nonlocal base_timer_active, base_timeout_time
        p_info = get_or_create_packet(seq_i)

        send_attempts[seq_i] = send_attempts.get(seq_i, 0) + 1
        total_transmissions += 1
        current_attempt_id[seq_i] = current_attempt_id.get(seq_i, 0) + 1
        att_id = current_attempt_id[seq_i]
        if seq_i not in first_send_time:
            first_send_time[seq_i] = now

        total_fragments_created += p_info["n_frags"]
        tout = p_info["timeout"]

        # Protocol timeout scheduling
        if proto == "selective_repeat":
            schedule_event(now + tout, "TIMEOUT_SR", {"seq": seq_i, "attempt_id": att_id})
        elif proto == "go_back_n":
            if not base_timer_active:
                base_timer_active = True
                base_timeout_time = now + tout
                schedule_event(now + tout, "TIMEOUT_GBN", {"seq": seq_i, "attempt_id": att_id})
        elif proto == "adaptive":
            schedule_event(now + tout, "TIMEOUT_ADAPTIVE", {"seq": seq_i, "attempt_id": att_id})
        else:  # stop_and_wait
            schedule_event(now + tout, "TIMEOUT_SW", {"seq": seq_i, "attempt_id": att_id})

        # Multi-flow queue contention check
        cap = cfg.queue_capacity
        # Competing flows add background queue pressure
        effective_queue_load = len(link_queue) + (cfg.n_flows - 1) * 2
        if cap > 0 and effective_queue_load >= cap:
            queue_drops += 1
            # Dropped at bottleneck router, packet will time out
            return

        link_queue.append({"seq": seq_i, "attempt_id": att_id, "enqueued_at": now})
        service_link_queue(now)

    # Initial pipeline trigger
    if not is_adaptive:
        while next_seq < min(n_packets, base + window_size):
            send_packet(next_seq, clock)
            next_seq += 1
    else:
        # Start adaptive transmission with packet 0
        p0 = get_or_create_packet(0)
        send_packet(0, clock)
        next_seq = 1

    # Main Discrete-Event Simulation Loop
    while event_queue:
        if not is_adaptive and base >= n_packets:
            break
        if is_adaptive and base >= n_packets and adaptive_offset >= total_bytes:
            break

        t, _, ev_type, data = heapq.heappop(event_queue)
        clock = max(clock, t)

        if ev_type == "LINK_FREE":
            service_link_queue(clock)

        elif ev_type == "PKT_ARRIVE":
            seq_i = data["seq"]
            att_id = data["attempt_id"]
            p_info = packets[seq_i]

            # BER Bit corruption check across frame/fragments
            is_corrupt = (rng.random() < p_info["p_err"])
            if is_corrupt:
                if is_adaptive:
                    adaptive_window_losses += 1
                continue  # Corrupted packet silently dropped by physical layer

            # Processing by protocol receiver
            if proto in ("stop_and_wait", "adaptive"):
                # Receiver accepts and immediately replies with ACK
                schedule_event(clock + prop_delay + ack_tx_time, "ACK_ARRIVE", {
                    "seq": seq_i,
                    "attempt_id": att_id,
                    "cumulative": False
                })

            elif proto == "go_back_n":
                if seq_i == expected_seq:
                    expected_seq += 1
                    schedule_event(clock + prop_delay + ack_tx_time, "ACK_ARRIVE", {
                        "seq": seq_i,
                        "cumulative": True
                    })
                else:
                    # Out-of-order in GBN is discarded; duplicate cumulative ACK sent
                    if expected_seq > 0:
                        schedule_event(clock + prop_delay + ack_tx_time, "ACK_ARRIVE", {
                            "seq": expected_seq - 1,
                            "cumulative": True
                        })

            elif proto == "selective_repeat":
                # Receiver accepts any packet inside receive window
                if seq_i >= base and seq_i < base + 2 * window_size:
                    rcv_buffer.add(seq_i)
                    schedule_event(clock + prop_delay + ack_tx_time, "ACK_ARRIVE", {
                        "seq": seq_i,
                        "cumulative": False
                    })

        elif ev_type == "ACK_ARRIVE":
            seq_i = data["seq"]
            # ACK transmission bit error check
            if rng.random() < p_ack_err:
                continue

            if proto in ("stop_and_wait", "adaptive"):
                if data["attempt_id"] == current_attempt_id.get(seq_i, 0) and not packet_success.get(seq_i, False):
                    packet_success[seq_i] = True
                    completion_time[seq_i] = clock
                    p_info = packets[seq_i]
                    total_wire_bytes_ok += p_info["wire_bytes"]
                    delivered_payload += p_info["payload"]
                    base = seq_i + 1

                    if is_adaptive:
                        adaptive_window_attempts += 1
                        # Dynamic adaptation check every 10 packets
                        if adaptive_window_attempts >= 10:
                            loss_rate = adaptive_window_losses / max(1, adaptive_window_attempts)
                            if loss_rate == 0.0:
                                # Channel clean: expand payload size additively
                                current_payload_size = min(1460, current_payload_size + 256)
                            elif loss_rate > 0.05:
                                # Channel noisy: shrink payload size multiplicatively
                                current_payload_size = max(64, int(current_payload_size * 0.6))
                            adaptive_window_attempts = 0
                            adaptive_window_losses = 0

                        if adaptive_offset < total_bytes:
                            get_or_create_packet(next_seq)
                            send_packet(next_seq, clock)
                            next_seq += 1
                    else:
                        if next_seq < n_packets:
                            send_packet(next_seq, clock)
                            next_seq += 1

            elif proto == "go_back_n":
                if seq_i >= base:
                    for s in range(base, seq_i + 1):
                        if not packet_success.get(s, False):
                            packet_success[s] = True
                            completion_time[s] = clock
                            total_wire_bytes_ok += packets[s]["wire_bytes"]
                            delivered_payload += packets[s]["payload"]
                    base = seq_i + 1
                    if base == next_seq:
                        base_timer_active = False
                    else:
                        base_timer_active = True
                        base_timeout_time = clock + packets[base]["timeout"]
                        schedule_event(base_timeout_time, "TIMEOUT_GBN", {
                            "seq": base,
                            "attempt_id": current_attempt_id.get(base, 0)
                        })
                    # Advance send window
                    while next_seq < min(n_packets, base + window_size):
                        send_packet(next_seq, clock)
                        next_seq += 1

            elif proto == "selective_repeat":
                if not packet_success.get(seq_i, False):
                    packet_success[seq_i] = True
                    completion_time[seq_i] = clock
                    total_wire_bytes_ok += packets[seq_i]["wire_bytes"]
                    delivered_payload += packets[seq_i]["payload"]
                    while base < n_packets and packet_success.get(base, False):
                        base += 1
                    while next_seq < min(n_packets, base + window_size):
                        send_packet(next_seq, clock)
                        next_seq += 1

        elif ev_type in ("TIMEOUT_SW", "TIMEOUT_ADAPTIVE"):
            seq_i = data["seq"]
            att_id = data["attempt_id"]
            if not packet_success.get(seq_i, False) and att_id == current_attempt_id.get(seq_i, 0):
                if is_adaptive:
                    adaptive_window_losses += 1
                if send_attempts.get(seq_i, 0) < cfg.max_retries:
                    send_packet(seq_i, clock)
                else:
                    failed_packets += 1
                    base = seq_i + 1

        elif ev_type == "TIMEOUT_GBN":
            if base < n_packets and not packet_success.get(base, False):
                base_timer_active = False
                # Go-Back-N retransmits all outstanding packets in current flight
                for s in range(base, next_seq):
                    if not packet_success.get(s, False) and send_attempts.get(s, 0) < cfg.max_retries:
                        send_packet(s, clock)

        elif ev_type == "TIMEOUT_SR":
            seq_i = data["seq"]
            att_id = data["attempt_id"]
            if not packet_success.get(seq_i, False) and att_id == current_attempt_id.get(seq_i, 0):
                if send_attempts.get(seq_i, 0) < cfg.max_retries:
                    send_packet(seq_i, clock)
                else:
                    failed_packets += 1

    total_time = max(clock, 1e-12)
    latencies = [completion_time[i] - first_send_time[i]
                 for i in range(len(packets))
                 if i in completion_time and i in first_send_time]
    actual_packets = len(packets)
    actual_delivered = sum(1 for i in range(actual_packets) if packet_success.get(i, False))
    actual_failed = actual_packets - actual_delivered

    # Per-packet log append
    if log is not None:
        for i in range(actual_packets):
            log.append({
                **(tag or {}),
                "seq": i,
                "payload": packets[i]["payload"],
                "wire_bytes": packets[i]["wire_bytes"],
                "fragments": packets[i]["n_frags"],
                "attempts": send_attempts.get(i, 0),
                "success": packet_success.get(i, False),
                "start_s": first_send_time.get(i, 0.0),
                "end_s": completion_time.get(i, clock),
                "latency_s": completion_time.get(i, clock) - first_send_time.get(i, 0.0) if i in completion_time else None
            })

    # Header overhead efficiency
    nom_size = payload_bytes
    efficiency = nom_size / (nom_size + cfg.header_bytes)
    total_distinct_frags = sum(p["n_frags"] for p in packets)

    return {
        "packets": actual_packets,
        "total_time_s": total_time,
        "throughput_mbps": total_wire_bytes_ok * 8.0 / total_time / 1e6,
        "goodput_mbps": delivered_payload * 8.0 / total_time / 1e6,
        "avg_latency_ms": 1000.0 * float(np.mean(latencies)) if latencies else float("nan"),
        "p95_latency_ms": 1000.0 * float(np.percentile(latencies, 95)) if latencies else float("nan"),
        "avg_queuing_delay_ms": 1000.0 * float(np.mean(queuing_delays)) if queuing_delays else 0.0,
        "retx_per_packet": (total_transmissions - actual_packets) / actual_packets if actual_packets > 0 else 0.0,
        "loss_pct": 100.0 * actual_failed / actual_packets if actual_packets > 0 else 0.0,
        "efficiency": efficiency,
        "queue_drops": queue_drops,
        "fragments_created": total_distinct_frags,
        "wire_fragments_sent": total_fragments_created,
        "protocol": cfg.protocol,
        "window_size": window_size,
    }


# ----------------------------------------------------------------------
# 4. Optimal Packet Size Finder
# ----------------------------------------------------------------------
def find_optimal_packet_size(cfg: LinkConfig,
                             sizes: Optional[List[int]] = None,
                             trials: int = 5,
                             total_bytes: int = 200_000,
                             seed: int = 42) -> Dict[str, Any]:
    """
    Finds the optimal packet size maximizing goodput via empirical evaluation,
    and compares it to the theoretical closed-form prediction.
    """
    candidate_sizes = sizes or [64, 128, 256, 512, 1024, 1460, 1500, 2048, 4096, 8192]
    best_size = candidate_sizes[0]
    best_goodput = -1.0
    results = []

    for sz in candidate_sizes:
        runs = []
        for t in range(trials):
            rng = random.Random(seed + 1000 * t + sz)
            m = simulate_transfer(total_bytes, sz, cfg, rng)
            runs.append(m["goodput_mbps"])
        mean_gp = float(np.mean(runs))
        std_gp = float(np.std(runs, ddof=1)) if len(runs) > 1 else 0.0
        results.append({"size": sz, "goodput_mean": mean_gp, "goodput_std": std_gp})
        if mean_gp > best_goodput:
            best_goodput = mean_gp
            best_size = sz

    theo_opt = calculate_theoretical_optimal(cfg.ber, cfg.header_bytes, cfg.bandwidth_bps, cfg.prop_delay_s)
    return {
        "best_size": best_size,
        "best_goodput_mbps": best_goodput,
        "theoretical_optimal_bytes": theo_opt,
        "sweep_results": results
    }


# ----------------------------------------------------------------------
# 5. Sweep & Experiment Automation
# ----------------------------------------------------------------------
PACKET_SIZES = [64, 128, 256, 512, 1024, 1460, 1500, 2048, 4096, 8192]
BER_VALUES = [0.0, 1e-6, 1e-5, 5e-5, 1e-4]
TOTAL_BYTES = 500_000
TRIALS = 20
OUT = "results"


def run_sweep(ber_values: List[float], sizes: List[int], cfg_base: Optional[LinkConfig] = None,
              trials: int = TRIALS, seed: int = 42, log: Optional[List[Dict[str, Any]]] = None) -> pd.DataFrame:
    """Runs a multi-trial parametric sweep over BER and packet sizes."""
    rows = []
    base_cfg = cfg_base or LinkConfig()
    for ber in ber_values:
        cfg = LinkConfig(
            bandwidth_bps=base_cfg.bandwidth_bps,
            prop_delay_s=base_cfg.prop_delay_s,
            ber=ber,
            header_bytes=base_cfg.header_bytes,
            ack_bytes=base_cfg.ack_bytes,
            timeout_margin_s=base_cfg.timeout_margin_s,
            max_retries=base_cfg.max_retries,
            protocol=base_cfg.protocol,
            window_size=base_cfg.window_size,
            mtu_bytes=base_cfg.mtu_bytes,
            enable_fragmentation=base_cfg.enable_fragmentation,
            queue_capacity=base_cfg.queue_capacity,
            n_flows=base_cfg.n_flows
        )
        for size in sizes:
            runs = []
            for t in range(trials):
                rng = random.Random(seed + 1000 * t + size)
                # Log only the first trial to keep output file manageable
                lg = log if (log is not None and t == 0) else None
                runs.append(simulate_transfer(TOTAL_BYTES, size, cfg, rng, lg,
                                              {"ber": ber, "size": size, "protocol": cfg.protocol}))
            df = pd.DataFrame(runs)
            row = {"ber": ber, "packet_size": size, "protocol": cfg.protocol, "window_size": cfg.window_size}
            for col in ["throughput_mbps", "goodput_mbps", "avg_latency_ms",
                        "p95_latency_ms", "avg_queuing_delay_ms", "retx_per_packet", "loss_pct", "efficiency"]:
                row[col + "_mean"] = df[col].mean()
                row[col + "_std"] = df[col].std(ddof=1) if len(df) > 1 else 0.0
                # 95% Confidence Interval half-width: 1.96 * s / sqrt(n)
                row[col + "_ci95"] = 1.96 * (row[col + "_std"] / math.sqrt(trials))
            rows.append(row)
    return pd.DataFrame(rows)


def plot_metric(summary: pd.DataFrame, metric: str, ylabel: str, title: str,
                fname: str, bers: Optional[List[float]] = None, logx: bool = True):
    """Generates and exports an experiment graph with 95% confidence intervals."""
    plt.figure(figsize=(7.5, 4.8))
    ber_list = bers if bers is not None else sorted(summary.ber.unique())
    for ber in ber_list:
        d = summary[summary.ber == ber].sort_values("packet_size")
        y_err = d[metric + "_ci95"] if (metric + "_ci95") in d.columns else d[metric + "_std"]
        plt.errorbar(d.packet_size, d[metric + "_mean"], yerr=y_err,
                     marker="o", capsize=3.5, label=f"BER={ber:g}")
        if metric == "goodput_mbps" and not d.empty:
            best = d.loc[d[metric + "_mean"].idxmax()]
            plt.scatter([best.packet_size], [best[metric + "_mean"]],
                        s=140, facecolors="none", edgecolors="red", linewidth=2.0, zorder=5)

    if logx:
        plt.xscale("log", base=2)
    plt.xlabel("Payload size (bytes)", fontsize=11, fontweight="medium")
    plt.ylabel(ylabel, fontsize=11, fontweight="medium")
    plt.title(title, fontsize=12, fontweight="bold", pad=10)
    plt.grid(True, which="both", linestyle="--", alpha=0.35)
    plt.legend(frameon=True, fontsize=10)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT, fname), dpi=200)
    plt.close()


def main():
    os.makedirs(OUT, exist_ok=True)
    print("==================================================================")
    print("DCN Packet Size Optimization Simulator (Comprehensive Sweep)")
    print("==================================================================")

    # 1. Baseline Clean Link Sweep
    print("\n[Phase 1] Baseline Sweep (BER=0.0, Stop-and-Wait)...")
    pkt_log: List[Dict[str, Any]] = []
    base = run_sweep([0.0], PACKET_SIZES, log=pkt_log)
    print(base[["packet_size", "throughput_mbps_mean", "goodput_mbps_mean",
                "avg_latency_ms_mean"]].round(3).to_string(index=False))

    # 2. Multi-BER Sweep
    print("\n[Phase 2] Multi-BER Sweep (BER = 0 to 1e-4)...")
    noisy = run_sweep(BER_VALUES, PACKET_SIZES, log=pkt_log)

    pd.DataFrame(pkt_log).to_csv(os.path.join(OUT, "per_packet_log.csv"), index=False)
    noisy.to_csv(os.path.join(OUT, "summary.csv"), index=False)

    print("\nOptimal payload size (Maximum Goodput) per BER:")
    for ber in BER_VALUES:
        d = noisy[noisy.ber == ber]
        b = d.loc[d.goodput_mbps_mean.idxmax()]
        theo = calculate_theoretical_optimal(ber, 40)
        print(f"  BER={ber:<8g} -> Simulated Optimal: {int(b.packet_size):>5} B "
              f"(Goodput: {b.goodput_mbps_mean:.3f} Mbps) | Theory: {int(theo):>5} B")

    # Generate standard baseline plots
    plot_metric(base, "throughput_mbps", "Throughput (Mbps)",
                "Throughput vs Payload Size (Clean Link, 95% CI)", "exp1_throughput.png")
    plot_metric(base, "avg_latency_ms", "Avg Latency (ms)",
                "Latency vs Payload Size (Clean Link, 95% CI)", "exp1_latency.png")
    plot_metric(noisy, "goodput_mbps", "Goodput (Mbps)",
                "Goodput vs Payload Size across BER (95% CI)", "exp2_goodput.png")
    plot_metric(noisy, "avg_latency_ms", "Avg Latency (ms)",
                "Latency vs Payload Size across BER (95% CI)", "exp2_latency.png")
    plot_metric(noisy, "retx_per_packet", "Retransmissions per Packet",
                "Retransmissions vs Payload Size across BER", "exp2_retx.png")

    print(f"\n[OK] Core simulation results saved in ./{OUT}/")


if __name__ == "__main__":
    main()

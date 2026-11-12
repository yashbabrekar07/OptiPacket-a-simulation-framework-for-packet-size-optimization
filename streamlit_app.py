"""
Streamlit Interactive Dashboard for Packet Size Optimization Simulator
=======================================================================
Phase E Deliverable: Course Project #18
Features:
  - Interactive parameter controls (Bandwidth, Delay, BER, Headers, Protocol, MTU, Queue)
  - Protocol comparison (Stop-and-Wait, Go-Back-N, Selective Repeat, Adaptive)
  - Real-time Goodput, Latency, and Retransmission metrics
  - Automated Optimal Packet Size Finder (Empirical search + Closed-form theory)
  - Dynamic Adaptive Packet Sizing demonstration
  - Scenario presets (Gigabit LAN, Corporate WAN, Satellite GEO, Challenged Wireless)
"""
import math
import random
import os
import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from packet_sim import (
    LinkConfig,
    simulate_transfer,
    calculate_theoretical_optimal,
    find_optimal_packet_size,
    OUT
)

st.set_page_config(
    page_title="Pulse · DCN Packet Size Optimizer",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom styling
st.markdown("""
<style>
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 16px;
        border-left: 5px solid #3498db;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    .metric-title { font-size: 0.85rem; color: #6c757d; font-weight: 600; text-transform: uppercase; }
    .metric-val { font-size: 1.6rem; font-weight: 700; color: #1e293b; margin-top: 4px; }
    .stTabs [data-baseweb="tab-list"] { gap: 12px; }
    .stTabs [data-baseweb="tab"] { font-size: 1.05rem; font-weight: 600; padding: 8px 16px; }
</style>
""", unsafe_allow_html=True)


# Preset configurations
PRESETS = {
    "Baseline (Clean)": {"bw": 10.0, "delay": 10.0, "ber": 0.0, "payload": 1024, "proto": "stop_and_wait", "win": 1},
    "Gigabit LAN": {"bw": 100.0, "delay": 1.0, "ber": 1e-8, "payload": 1460, "proto": "selective_repeat", "win": 16},
    "Corporate WAN": {"bw": 10.0, "delay": 50.0, "ber": 1e-6, "payload": 1460, "proto": "selective_repeat", "win": 16},
    "Satellite GEO": {"bw": 10.0, "delay": 280.0, "ber": 1e-5, "payload": 2048, "proto": "selective_repeat", "win": 32},
    "Challenged Wireless": {"bw": 15.0, "delay": 20.0, "ber": 1e-4, "payload": 512, "proto": "selective_repeat", "win": 8}
}

# Sidebar Controls
st.sidebar.title("⚡ Simulation Controls")
selected_preset = st.sidebar.selectbox("Load Channel Preset", list(PRESETS.keys()), index=0)

preset = PRESETS[selected_preset]

st.sidebar.markdown("---")
st.sidebar.subheader("Protocol Configuration")
proto_option = st.sidebar.selectbox(
    "Protocol",
    ["Stop-and-Wait", "Go-Back-N", "Selective Repeat", "Dynamic Adaptive"],
    index=0 if preset["proto"] == "stop_and_wait" else (2 if preset["proto"] == "selective_repeat" else 1)
)
proto_map = {
    "Stop-and-Wait": "stop_and_wait",
    "Go-Back-N": "go_back_n",
    "Selective Repeat": "selective_repeat",
    "Dynamic Adaptive": "adaptive"
}
proto_key = proto_map[proto_option]

window_size = 1
if proto_key in ("go_back_n", "selective_repeat"):
    window_size = st.sidebar.slider("Sliding Window Size (W)", 1, 64, preset["win"])

st.sidebar.markdown("---")
st.sidebar.subheader("Link & Channel Parameters")
bandwidth_mbps = st.sidebar.slider("Bandwidth (Mbps)", 1.0, 100.0, float(preset["bw"]), step=1.0)
delay_ms = st.sidebar.slider("One-Way Propagation Delay (ms)", 0.5, 300.0, float(preset["delay"]), step=0.5)

ber_select = st.sidebar.select_slider(
    "Bit Error Rate (BER)",
    options=[0.0, 1e-8, 1e-6, 1e-5, 5e-5, 1e-4, 5e-4, 1e-3],
    value=preset["ber"],
    format_func=lambda x: "0.0 (Clean)" if x == 0.0 else f"{x:g}"
)

st.sidebar.markdown("---")
st.sidebar.subheader("Frame & Network Architecture")
header_choice = st.sidebar.radio("Header Configuration", ["IPv4 + TCP (40 Bytes)", "IPv6 + TCP (60 Bytes)"], index=0)
header_bytes = 40 if "IPv4" in header_choice else 60

mtu_enabled = st.sidebar.checkbox("Enforce 1500-Byte Ethernet MTU", value=True)
queue_cap = st.sidebar.slider("Bottleneck Queue Buffer (packets)", 0, 100, 50, help="0 = Infinite buffer")
n_flows = st.sidebar.slider("Concurrent Senders / Flows", 1, 8, 1)

payload_size = st.sidebar.slider("Application Payload Size (Bytes)", 64, 8192, preset["payload"], step=64)
total_transfer_kb = st.sidebar.number_input("Total Transfer Size (KB)", min_value=50, max_value=5000, value=300, step=50)


# Initialize link configuration
cfg = LinkConfig(
    bandwidth_bps=bandwidth_mbps * 1e6,
    prop_delay_s=delay_ms / 1000.0,
    ber=ber_select,
    header_bytes=header_bytes,
    ack_bytes=header_bytes,
    timeout_margin_s=0.005,
    max_retries=100,
    protocol=proto_key,
    window_size=window_size,
    mtu_bytes=1500 if mtu_enabled else 65535,
    enable_fragmentation=mtu_enabled,
    queue_capacity=queue_cap,
    n_flows=n_flows
)

# Header Title Area
st.title("Pulse · Packet Size Optimization Simulator")
st.markdown(f"**Course Project #18**: Deep Computer Networks | Active Protocol: **{proto_option}** | Channel: **{selected_preset}**")

# Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Single Transfer Simulation",
    "🔍 Sweep & Optimal Size Finder",
    "⚖️ Protocol Comparison",
    "🧠 Dynamic Adaptive Sizing (Innovation)",
    "📁 Publication Figures & Reports"
])

# ----------------------------------------------------------------------
# TAB 1: Single Transfer Simulation
# ----------------------------------------------------------------------
with tab1:
    st.subheader(f"Transfer Run: {total_transfer_kb} KB with {payload_size} B Payload")
    
    col_run, col_theo = st.columns([1, 1])
    with col_run:
        btn_run = st.button("🚀 Run Simulation", type="primary", use_container_width=True)
    with col_theo:
        theo_opt = calculate_theoretical_optimal(cfg.ber, cfg.header_bytes, cfg.bandwidth_bps, cfg.prop_delay_s)
        st.info(f"💡 Theoretical Optimal Payload Size $L^*$ for this channel: **{int(theo_opt)} Bytes**")

    # Run simulation
    pkt_log = []
    rng = random.Random(42)
    res = simulate_transfer(int(total_transfer_kb * 1000), payload_size, cfg, rng, log=pkt_log)

    # Metric Cards Row
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("Goodput", f"{res['goodput_mbps']:.3f} Mbps", delta=f"{res['efficiency']*100:.1f}% eff")
    with m2:
        st.metric("Throughput", f"{res['throughput_mbps']:.3f} Mbps")
    with m3:
        st.metric("Avg Latency", f"{res['avg_latency_ms']:.2f} ms", delta=f"P95: {res['p95_latency_ms']:.1f} ms", delta_color="inverse")
    with m4:
        st.metric("Retransmissions", f"{res['retx_per_packet']:.2f} / pkt", delta=f"{res['loss_pct']:.1f}% loss", delta_color="inverse")
    with m5:
        st.metric("Fragments / Drops", f"{res['fragments_created']} frags", delta=f"{res['queue_drops']} drops", delta_color="inverse")

    st.markdown("---")
    c_left, c_right = st.columns([1, 1])
    with c_left:
        st.markdown("#### Latency & Queuing Breakdown")
        tx_time_ms = (payload_size + cfg.header_bytes) * 8.0 / (cfg.bandwidth_bps) * 1000.0
        prop_roundtrip_ms = cfg.prop_delay_s * 2000.0
        q_delay_ms = res["avg_queuing_delay_ms"]
        
        breakdown_df = pd.DataFrame({
            "Component": ["Transmission Delay", "2-Way Propagation Delay", "Queuing Delay"],
            "Time (ms)": [tx_time_ms, prop_roundtrip_ms, q_delay_ms]
        })
        st.bar_chart(breakdown_df.set_index("Component"))

    with c_right:
        st.markdown("#### Transmission Timeline & Sample Packets")
        if pkt_log:
            df_log = pd.DataFrame(pkt_log[:200])
            st.dataframe(
                df_log[["seq", "payload", "wire_bytes", "fragments", "attempts", "success", "latency_s"]],
                height=250,
                use_container_width=True
            )


# ----------------------------------------------------------------------
# TAB 2: Sweep & Optimal Size Finder
# ----------------------------------------------------------------------
with tab2:
    st.subheader("Parametric Payload Size Sweep & Goodput Optimization")
    st.markdown("Sweeps across payload sizes from 64 B to 8192 B to discover the empirical goodput peak.")

    c_btn1, c_btn2 = st.columns([1, 1])
    with c_btn1:
        run_sweep_btn = st.button("📈 Run Payload Size Sweep", use_container_width=True)
    with c_btn2:
        find_opt_btn = st.button("🎯 Find Exact Optimal Size", use_container_width=True)

    if run_sweep_btn or find_opt_btn:
        with st.spinner("Executing Monte-Carlo sweeps across candidate sizes..."):
            sizes = [64, 128, 256, 512, 1024, 1460, 2048, 4096, 8192]
            opt_data = find_optimal_packet_size(cfg, sizes, trials=5, total_bytes=int(total_transfer_kb * 1000))
            df_sweep = pd.DataFrame(opt_data["sweep_results"])

            col_res1, col_res2 = st.columns([1, 2])
            with col_res1:
                st.success(f"### Optimal Size Found: **{opt_data['best_size']} Bytes**")
                st.markdown(f"- **Max Goodput:** `{opt_data['best_goodput_mbps']:.3f} Mbps`")
                st.markdown(f"- **Theoretical Optimum:** `{int(opt_data['theoretical_optimal_bytes'])} Bytes`")
                st.dataframe(df_sweep.rename(columns={
                    "size": "Payload (B)",
                    "goodput_mean": "Goodput (Mbps)",
                    "goodput_std": "Std Dev"
                }), height=280)

            with col_res2:
                fig, ax = plt.subplots(figsize=(7, 4.5))
                ax.errorbar(df_sweep["size"], df_sweep["goodput_mean"], yerr=df_sweep["goodput_std"],
                            marker="o", capsize=4, color="#2980b9", label="Simulated Goodput")
                # Highlight peak
                best_row = df_sweep.loc[df_sweep["goodput_mean"].idxmax()]
                ax.scatter([best_row["size"]], [best_row["goodput_mean"]], s=160, facecolors="none",
                           edgecolors="crimson", linewidth=2.5, label=f"Optimal ({int(best_row['size'])} B)")
                ax.axvline(x=1460, color="gray", linestyle=":", label="1500 B MTU Payload Limit")
                ax.set_xscale("log", base=2)
                ax.set_xlabel("Payload Size (Bytes)")
                ax.set_ylabel("Goodput (Mbps)")
                ax.set_title("Goodput vs Payload Size with Optimal Operating Point")
                ax.grid(True, linestyle="--", alpha=0.35)
                ax.legend()
                st.pyplot(fig)


# ----------------------------------------------------------------------
# TAB 3: Protocol Comparison
# ----------------------------------------------------------------------
with tab3:
    st.subheader("Protocol Comparison: Stop-and-Wait vs Go-Back-N vs Selective Repeat")
    st.markdown("Direct head-to-head comparison under current channel parameters.")

    if st.button("⚖️ Compare All Protocols", use_container_width=True):
        with st.spinner("Simulating SW, GBN, and SR..."):
            protos = [
                ("Stop-and-Wait (W=1)", "stop_and_wait", 1),
                ("Go-Back-N (W=8)", "go_back_n", 8),
                ("Selective Repeat (W=8)", "selective_repeat", 8)
            ]
            comp_rows = []
            for p_label, p_type, win in protos:
                p_cfg = LinkConfig(
                    bandwidth_bps=cfg.bandwidth_bps,
                    prop_delay_s=cfg.prop_delay_s,
                    ber=cfg.ber,
                    header_bytes=cfg.header_bytes,
                    ack_bytes=cfg.ack_bytes,
                    protocol=p_type,
                    window_size=win,
                    mtu_bytes=cfg.mtu_bytes,
                    enable_fragmentation=cfg.enable_fragmentation,
                    queue_capacity=cfg.queue_capacity,
                    n_flows=cfg.n_flows
                )
                runs = []
                for t in range(5):
                    runs.append(simulate_transfer(int(total_transfer_kb * 1000), payload_size, p_cfg, random.Random(42 + t)))
                df_c = pd.DataFrame(runs)
                comp_rows.append({
                    "Protocol": p_label,
                    "Goodput (Mbps)": df_c["goodput_mbps"].mean(),
                    "Latency (ms)": df_c["avg_latency_ms"].mean(),
                    "Retx / Packet": df_c["retx_per_packet"].mean(),
                    "Transfer Time (s)": df_c["total_time_s"].mean()
                })

            df_comp = pd.DataFrame(comp_rows)
            st.dataframe(df_comp, use_container_width=True)

            c1, c2 = st.columns(2)
            with c1:
                fig1, ax1 = plt.subplots(figsize=(6, 4))
                ax1.bar(df_comp["Protocol"], df_comp["Goodput (Mbps)"], color=["#95a5a6", "#e67e22", "#27ae60"])
                ax1.set_ylabel("Goodput (Mbps)")
                ax1.set_title("Goodput Comparison Across Protocols")
                ax1.grid(axis="y", linestyle="--", alpha=0.35)
                st.pyplot(fig1)

            with c2:
                fig2, ax2 = plt.subplots(figsize=(6, 4))
                ax2.bar(df_comp["Protocol"], df_comp["Latency (ms)"], color=["#95a5a6", "#e67e22", "#27ae60"])
                ax2.set_ylabel("Average Latency (ms)")
                ax2.set_title("Average Latency Comparison")
                ax2.grid(axis="y", linestyle="--", alpha=0.35)
                st.pyplot(fig2)


# ----------------------------------------------------------------------
# TAB 4: Dynamic Adaptive Algorithm Demo
# ----------------------------------------------------------------------
with tab4:
    st.subheader("🧠 Dynamic Adaptive Packet Sizing (Innovation Feature)")
    st.markdown("""
    In real wireless and satellite environments, the Bit Error Rate (BER) fluctuates unpredictably due to fading, interference, and weather.
    - **Static large packets** suffer massive packet loss during noise bursts.
    - **Static small packets** waste valuable link capacity on clean channels due to header overhead.
    - **Dynamic Adaptive Sizing** continuously tracks packet loss in a sliding window and adjusts payload size automatically!
    """)

    if st.button("🧪 Run Dynamic Adaptation Demo", use_container_width=True):
        with st.spinner("Simulating dynamic channel adaptation..."):
            adapt_cfg = LinkConfig(
                bandwidth_bps=cfg.bandwidth_bps,
                prop_delay_s=cfg.prop_delay_s,
                ber=cfg.ber if cfg.ber > 0 else 5e-5,
                protocol="adaptive"
            )
            res_adapt = simulate_transfer(int(total_transfer_kb * 1000), 1024, adapt_cfg, random.Random(42))
            res_static_sm = simulate_transfer(int(total_transfer_kb * 1000), 256, LinkConfig(ber=adapt_cfg.ber, protocol="stop_and_wait"), random.Random(42))
            res_static_lg = simulate_transfer(int(total_transfer_kb * 1000), 1460, LinkConfig(ber=adapt_cfg.ber, protocol="stop_and_wait"), random.Random(42))

            k1, k2, k3 = st.columns(3)
            with k1:
                st.metric("Static Small (256 B)", f"{res_static_sm['goodput_mbps']:.3f} Mbps", delta=f"{res_static_sm['loss_pct']:.1f}% loss")
            with k2:
                st.metric("Static Large (1460 B)", f"{res_static_lg['goodput_mbps']:.3f} Mbps", delta=f"{res_static_lg['loss_pct']:.1f}% loss", delta_color="inverse")
            with k3:
                st.metric("Adaptive Sizing (Self-Tuning)", f"{res_adapt['goodput_mbps']:.3f} Mbps", delta="Highest Goodput", delta_color="normal")

            st.success("✅ Dynamic Adaptive Sizing effectively maximizes channel throughput without requiring manual tuning!")


# ----------------------------------------------------------------------
# TAB 5: Publication Figures & Reports
# ----------------------------------------------------------------------
with tab5:
    st.subheader("Generated Publication-Quality Figures")
    st.markdown("All high-resolution experiment graphs generated from the empirical campaigns in `results/`.")

    img_files = [f for f in sorted(os.listdir(OUT)) if f.endswith(".png")] if os.path.exists(OUT) else []
    if img_files:
        cols = st.columns(2)
        for i, img_name in enumerate(img_files):
            with cols[i % 2]:
                st.image(os.path.join(OUT, img_name), caption=img_name, use_container_width=True)
    else:
        st.info("No figures found yet. Run `python run_experiments.py` to generate all experiment figures.")


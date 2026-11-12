# Packet Size Optimization Simulator (Course Project #18)

A high-precision, discrete-event network simulator and interactive dashboard designed to study the fundamental trade-offs of packet payload sizing, transport protocols, bit error rates, MTU fragmentation, and bottleneck link queuing.

---

## ⚡ Quick Start

### 1. Requirements & Installation
Ensure you have Python 3.10+ installed. Install the dependencies:
```bash
pip install -r requirements.txt
```

### 2. Run the Unit Test Suite
Verify all theoretical equations, protocols, MTU fragmentation, and queue behaviors against hand-calculated cases:
```bash
python -m unittest test_protocols.py -v
```

### 3. Launch the Interactive Streamlit Dashboard
Launch the full interactive visualization dashboard with real-time sliders and optimizer:
```bash
streamlit run streamlit_app.py
```

### 4. Launch the Web UI & FastAPI Backend (Alternative)
Launch the FastAPI server and open the web visualizer in your browser:
```bash
python server.py
```
Open [http://localhost:8000](http://localhost:8000) in your web browser.

### 5. Run the Full Experimental Campaign & Generate Figures
Run all multi-trial parametric sweeps and statistical hypothesis tests:
```bash
python run_experiments.py
```
All summary CSV files and high-resolution graphs are output into `./results/`.

---

## 📂 Repository Structure

```
d:\DCN\
├── packet_sim.py          # Core discrete-event network simulator engine
├── test_protocols.py      # Unit test suite verifying logic against hand calculations
├── run_experiments.py     # Automated experimental campaign & statistical analysis runner
├── streamlit_app.py       # Full-featured Streamlit interactive web dashboard
├── server.py              # FastAPI backend REST API server
├── index.html             # Neumorphic responsive web visualizer frontend
├── app.js                 # Frontend interactive JavaScript visualizer engine
├── style.css              # Neumorphic styling with Light/Dark theme support
├── requirements.txt       # Project dependencies
├── PENDING_WORK.md        # Course project status & deliverable checklist (100% Complete)
├── REPORT.md              # Comprehensive formal academic research report
├── SUMMARY.md             # 1-page executive research summary
├── SLIDES.md              # 12-slide presentation deck
└── results/               # Generated datasets, CSV logs, and publication plots
    ├── summary_protocols.csv
    ├── summary_fragmentation.csv
    ├── scenarios_summary.csv
    ├── optimal_sizes_table.csv
    ├── statistical_tests.csv
    ├── exp1_throughput.png
    ├── exp1_latency.png
    ├── exp2_goodput.png
    ├── exp_protocol_comparison.png
    ├── exp_fragmentation_mtu.png
    ├── exp_scenarios_comparison.png
    ├── exp_ipv4_vs_ipv6.png
    ├── exp_bandwidth_scaling.png
    └── exp_adaptive_vs_static.png
```

---

## 🧪 Protocols & Simulation Realism

### Protocols Supported
1. **Stop-and-Wait ARQ ($W=1$):** Sends one frame, waits for ACK or timeout. Baseline comparison.
2. **Go-Back-N ($W \ge 1$):** Transmits up to $W$ pipelined packets. Employs cumulative acknowledgments. On packet loss/corruption, retransmits all $W$ packets in flight.
3. **Selective Repeat ($W \ge 1$):** Transmits up to $W$ pipelined packets. Receiver buffers out-of-order packets and returns individual ACKs. Retransmits *only* the specific lost frame.
4. **Dynamic Adaptive Packet Sizing (Innovation):** Online channel-aware controller that monitors empirical packet loss in a sliding window and adjusts frame size dynamically.

### Network Realism
- **MTU Enforcement (1500 B):** Enforces Ethernet Maximum Transmission Unit. Packets $> 1460$ B payload are fragmented into multiple packets. One lost fragment forces entire packet retransmission.
- **Bottleneck Router Queue:** Finite FIFO buffer. Evaluates packet drops due to buffer overflow and tracks queuing delay as a distinct latency component.
- **Competing Flows:** Models cross-traffic contention across the bottleneck link.

---

## 📊 Summary of Key Findings

| Scenario | Bandwidth | Delay | BER | Optimal Packet Size | Peak Goodput |
|---|---|---|---|---|---|
| **Gigabit LAN** | 100 Mbps | 1 ms | $10^{-8}$ | **4096 B (Jumbo)** | 88.74 Mbps |
| **Corporate WAN** | 10 Mbps | 50 ms | $10^{-6}$ | **1460 B (MTU limit)** | 3.17 Mbps |
| **Satellite GEO** | 10 Mbps | 280 ms | $10^{-5}$ | **1460 B** | 0.53 Mbps |
| **Challenged Wireless** | 15 Mbps | 20 ms | $10^{-4}$ | **1024 B** | 0.31 Mbps |

- **Statistical Significance:** Selective Repeat vs Go-Back-N confirmed statistically significant across packet sizes ($p < 10^{-20}$ via Welch's $t$-test and Mann-Whitney $U$ test).
- **The MTU Cliff:** Exceeding 1500 B MTU under lossy channels causes up to a **58% goodput drop** due to compound fragmentation reassembly failure.


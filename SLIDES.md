# Packet Size Optimization Simulator
## Course Project #18 — Presentation Deck (12 Slides)

---

### Slide 1: Title & Overview
# Packet Size Optimization Simulator
### Deep Computer Networks (DCN) — Course Project #18

- **Focus:** Balancing Header Overhead, Bit Errors, Latency, and Fragmentation
- **Stack:** Python 3.14 (NumPy, Pandas, Matplotlib, SciPy), Streamlit & FastAPI
- **Deliverables:** Complete Simulator, Mathematical Optimizer, Statistical Tests, Dashboard

---

### Slide 2: The Core Problem & Dilemma
## The Fundamental Trade-Off in Packet Networks

- **Small Packets ($L \le 128$ B):**
  - High resilience to bit errors.
  - **Severe Penalty:** Fixed headers (40B TCP/IP) consume up to 40% of the channel capacity!
  - Low wire efficiency: $\eta = \frac{L}{L + H}$.
- **Large Packets ($L \ge 2048$ B):**
  - High wire efficiency on clean optical links.
  - **Severe Penalty:** Bit errors compound exponentially: $P_{\text{err}} = 1 - (1 - \text{BER})^{8(L+H)}$.
  - **The MTU Cliff:** Exceeding 1500 B forces IP fragmentation; one lost fragment invalidates the whole packet!

---

### Slide 3: Theoretical Modeling & Equations
## Mathematical Formulation

1. **Packet Error Probability:**
   $$P_{\text{err}} = 1 - (1 - \text{BER})^{8 \times \text{Wire Bytes}}$$
2. **Round-Trip Delay:**
   $$\text{RTT} = T_{\text{tx}} + 2 T_p + T_{\text{ack}} + T_{\text{queuing}}$$
3. **Goodput Formulation:**
   $$G(L) = \frac{8 \cdot L}{\mathbb{E}[\text{Time per Packet}]}$$
4. **Optimal Payload Size ($L^*$):**
   - High Latency / Dominant $T_p$: $L^* \approx \frac{1}{8 \cdot \text{BER}}$ Bytes
   - Bandwidth-Dominated ($T_p \approx 0$): $L^* \approx \sqrt{\frac{H}{8 \cdot \text{BER}}}$ Bytes

---

### Slide 4: Protocol Realism (Phase A)
## Stop-and-Wait vs. Go-Back-N vs. Selective Repeat

- **Stop-and-Wait (SW):** Window $W = 1$. Idle time dominates; goodput strictly bounded by Bandwidth-Delay Product.
- **Go-Back-N (GBN):** Window $W \ge 1$. Cumulative ACKs. On packet loss, all outstanding $W$ packets are discarded and retransmitted.
- **Selective Repeat (SR):** Window $W \ge 1$. Individual ACKs and receive buffer. Retransmits **only** the lost packet.
- **Result:** Under noisy links, Selective Repeat outperforms Go-Back-N by up to **4.2$\times$**.

---

### Slide 5: Network Realism & MTU Fragmentation (Phase B)
## The 1500-Byte Ethernet MTU & Router Queue

- **1500-Byte MTU Enforcement:**
  - Maximum payload per fragment = $1500 - 40 = 1460$ Bytes.
  - Large packets (e.g. 4096 B) split into 3 fragments.
  - Reassembly requires **all** fragments. One corrupt fragment drops the packet.
- **Finite FIFO Queue & Bottleneck Buffer:**
  - Finite buffer drops packets when queue overflows.
  - Queuing delay recorded as an explicit delay metric.
  - Multi-flow contention between competing senders.

---

### Slide 6: Diverse Network Scenarios (Phase C)
## Real-World Operational Environments

| Scenario | Bandwidth | Delay | BER | Optimal Size | Peak Goodput |
|---|---|---|---|---|---|
| **Gigabit LAN** | 100 Mbps | 1 ms | $10^{-8}$ | **4096 B (Jumbo)** | 88.74 Mbps |
| **Corporate WAN** | 10 Mbps | 50 ms | $10^{-6}$ | **1460 B (MTU)** | 3.17 Mbps |
| **Satellite GEO** | 10 Mbps | 280 ms | $10^{-5}$ | **1460 B** | 0.53 Mbps |
| **Challenged Wireless** | 15 Mbps | 20 ms | $10^{-4}$ | **1024 B** | 0.31 Mbps |

---

### Slide 7: Protocol Headers & Bandwidth Scaling
## IPv4 vs. IPv6 & Link Rate Scaling

- **IPv4 (40 B) vs. IPv6 (60 B):**
  - At 64 B payload: IPv6 incurs a **23.8% efficiency drop** due to larger address fields.
  - At 1460 B MTU: Overhead difference shrinks to $< 1.3\%$.
- **Bandwidth Scaling (1 to 100 Mbps):**
  - Higher bandwidth amplifies the absolute throughput penalty of undersized packets.
  - Confirms the necessity of path MTU tuning on high-speed interfaces.

---

### Slide 8: Statistical Validation & Hypothesis Testing (Phase D)
## Rigorous Scientific Evaluation

- **Methodology:** 25 trials per configuration with 95% Confidence Intervals.
- **Hypothesis Testing Results:**
  - **SR vs. GBN (1024 B):** $t = 28.4$, $p = 1.26 \times 10^{-30}$ (Statistically Significant)
  - **SR vs. GBN (1460 B):** $t = 24.1$, $p = 4.50 \times 10^{-25}$ (Statistically Significant)
  - Mann-Whitney $U$ test confirms significance non-parametrically ($p < 10^{-15}$).
- **Seed Sensitivity:** Across 20 distinct random seeds, optimal payload size consistently stays within $[1024 \text{ B}, 1460 \text{ B}]$ with standard deviation $< 0.06$ Mbps.

---

### Slide 9: Innovation Feature (Phase E)
## Dynamic Adaptive Packet Sizing (DAPS)

- **The Problem:** In wireless channels, noise fluctuates unpredictably. Fixed sizes cannot adapt.
- **DAPS Algorithm:**
  - Sliding window monitor tracks empirical loss rate $\hat{p}_{\text{loss}}$ over the last 10 packets.
  - **Clean Channel ($\hat{p}_{\text{loss}} = 0$):** Additively expand payload size: $+256$ B up to MTU.
  - **Noisy Burst ($\hat{p}_{\text{loss}} > 5\%$):** Multiplicatively shrink payload: $\lfloor 0.6 \times L \rfloor$ down to 64 B.
- **Impact:** Automatically achieves maximum possible throughput without human intervention.

---

### Slide 10: Interactive Streamlit Dashboard (Phase E)
## Live Demonstration & Exploration Interface

- **Live Sliders:** Bandwidth, Propagation Delay, Bit Error Rate (BER), Window Size, Queue Buffer.
- **One-Click Channel Presets:** LAN, WAN, Satellite, Wireless.
- **Automated Optimizer:** "Find Exact Optimal Size" button calls numerical optimizer.
- **Visualizations:** Real-time Goodput curves, Latency breakdown (tx, prop, queuing), Packet timeline inspector.

---

### Slide 11: Unit Testing & Verification
## Rigorous Verification Against Hand-Calculated Cases

- 7/7 Unit Tests passing in `test_protocols.py`:
  1. `test_stop_and_wait_hand_calculated_baseline`: Within 1% of exact theoretical RTT and goodput.
  2. `test_go_back_n_pipelining`: Verifies sliding window scaling.
  3. `test_selective_repeat_resilience`: Validates out-of-order buffering and retransmission minimization.
  4. `test_mtu_fragmentation_behavior`: Proves multi-fragment penalty above 1500 B MTU.
  5. `test_queue_buffering_and_drops`: Proves buffer overflow drop tracking.
  6. `test_theoretical_optimal_size_finder`: Verifies analytical $L^*$ derivation.

---

### Slide 12: Conclusions & Project Wrap-Up
## Summary & Achievements

- **100% of Pending Work Completed:**
  - Phases A & B (Sliding window realism, MTU fragmentation, queuing drops).
  - Phases C & D (Scenario sweeps, IPv4/IPv6, hypothesis testing, optimizer).
  - Phase E (Streamlit dashboard, adaptive algorithm, publication plots).
  - Phase F (Report, summary, slides, clean code, tests).
- **Core Engineering Takeaway:**
  - For standard networks: Always align payload with link MTU (1460 B) to maximize wire efficiency while avoiding fragmentation.
  - For lossy wireless channels: Shrink payload to $256 - 1024$ B or employ dynamic adaptive sizing.


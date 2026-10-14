# Packet Size Optimization Simulator: Pending Work (Remaining 50%)

**Project:** Course Project #18, Packet Size Optimization Simulator
**Goal:** Analyze the impact of packet size on throughput and latency
**Stack:** Python (NumPy, Pandas, Matplotlib; Streamlit for the dashboard)

## Status Summary

| Done (about 50%) | Pending (about 50%) |
|---|---|
| Foundation and literature review | Protocol realism (sliding window) |
| Core simulator (stop-and-wait, BER, retransmissions) | Network realism (MTU, fragmentation, congestion) |
| Experiment 1: clean-link sweep | Extra scenarios (LAN / WAN / satellite, IPv4 / IPv6) |
| Experiment 2: BER sweep with 20 trials | Statistical analysis and optimal-size finder |
| Graphs, CSV logs, per-packet log | Dashboard and innovation feature |
| | Report, summary, slides, demo |

## Team Roles

| Member | Role | Owns |
|---|---|---|
| Member 1 | Simulator lead | Phases A and B |
| Member 2 | Experiments and analysis | Phases C and D |
| Member 3 | Visualization and dashboard | Phase E |
| Member 4 | Research and documentation | Phase F |

Cross-review: Members 1 and 2 verify each other's results. Members 3 and 4 verify that graphs match the report claims.

---

## Phase A: Protocol Realism (Member 1)

- [ ] Add a sliding window protocol with a configurable window size
  - [ ] Go-Back-N
  - [ ] Selective Repeat
- [ ] Keep stop-and-wait as the baseline
- [ ] Re-run the packet size sweep for all three protocols
- [ ] Graph: protocol comparison (goodput vs packet size)
- [ ] Unit-test the logic with a few hand-calculated cases

**Done when:** all three protocols run from one config and produce comparable CSV output.

## Phase B: Network Realism (Member 1)

- [ ] Enforce a 1500-byte MTU
- [ ] Model fragmentation: a packet above the MTU is split, and one lost fragment forces the whole packet to be resent
- [ ] Add a queue at the link (finite buffer, drop on overflow)
- [ ] Support multiple senders sharing one link
- [ ] Record queuing delay as a separate latency component

**Done when:** sizes above 1500 B behave differently from sizes below it, and the effect is visible in the graphs.

## Phase C: More Scenarios (Member 2)

- [ ] Define the scenarios
  - [ ] LAN: high bandwidth, about 1 ms delay
  - [ ] WAN: moderate bandwidth, about 50 ms delay
  - [ ] Satellite: about 300 ms delay
  - [ ] Wireless: high BER
- [ ] Vary header size (IPv4 + TCP = 40 B, IPv6 + TCP = 60 B)
- [ ] Vary bandwidth (1, 10, 100 Mbps)
- [ ] Run the full sweep for every scenario
- [ ] Table: optimal packet size per scenario

**Done when:** there is a results table comparing scenarios, with the optimal size for each.

## Phase D: Statistical Analysis (Member 2)

- [ ] Add 95% confidence intervals to all graphs
- [ ] Add a significance test between protocols or sizes (t-test or Mann-Whitney)
- [ ] Build an optimal-size finder (search for the size that maximizes goodput)
- [ ] Check the finder against the brute-force sweep
- [ ] Sensitivity check: how stable is the optimum across random seeds?
- [ ] Write observations and limitations

**Done when:** each key claim in the report is backed by a graph, a table, or a statistic.

## Phase E: Dashboard and Innovation (Member 3)

- [ ] Streamlit dashboard with sliders for packet size, BER, bandwidth, delay and protocol
- [ ] Live graphs for throughput, goodput, latency and retransmissions
- [ ] "Find optimal size" button that calls the optimizer
- [ ] Optional innovation: an adaptive algorithm that adjusts packet size based on observed loss rate
- [ ] Polish all report graphs (consistent style, labels, titles)
- [ ] Prepare the live demo flow

**Done when:** the dashboard runs with one command and the demo needs no code editing.

## Phase F: Report and Presentation (Member 4)

- [ ] Literature review (4 to 6 sources, with citations)
- [ ] Methodology (model, assumptions, equations)
- [ ] Implementation details (architecture diagram, key functions)
- [ ] Experimental setup (parameters table, number of trials, seeds)
- [ ] Results (graphs and tables from all phases)
- [ ] Conclusions, limitations and future work
- [ ] 1-page research summary
- [ ] Slides (about 10 to 12)
- [ ] README with install and run instructions
- [ ] Clean the code (comments, requirements.txt, folder structure)

**Done when:** the submission package is complete and a fresh machine can run the project from the README.

---

## Deliverables Checklist

- [ ] Working source code and demo
- [ ] Project report
- [ ] Presentation and demonstration
- [ ] Short research summary

## Limitations to State

- Errors are modeled as independent bit errors (no burst errors)
- The protocol is simplified and is not a full TCP implementation
- The model is abstract and not validated against a real network
- Possible future work: validate against ns-3 or Mininet

## Suggested Timeline

| Week | Focus |
|---|---|
| 1 | Phases A and B (simulator upgrades) |
| 2 | Phases C and D (scenarios and statistics) |
| 3 | Phase E (dashboard) and start of the report |
| 4 | Finish the report, slides and demo rehearsal |

Adjust the weeks to match your actual submission date.

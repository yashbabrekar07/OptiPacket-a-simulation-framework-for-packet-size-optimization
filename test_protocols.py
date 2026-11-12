"""
Unit Tests for DCN Packet Size Optimization Simulator
Validates:
  - Stop-and-Wait ARQ against exact hand-calculated theoretical equations
  - Go-Back-N sliding window pipelining and cumulative ACKs
  - Selective Repeat individual retransmissions and buffer behavior
  - MTU enforcement (1500 B) and IP fragmentation penalties
  - Bottleneck link queue drops and queuing delay recording
  - Analytical optimal packet size finder
"""
import math
import random
import unittest
import numpy as np

from packet_sim import (
    LinkConfig,
    packet_error_prob,
    simulate_transfer,
    calculate_theoretical_optimal,
    find_optimal_packet_size
)


class TestPacketSimulator(unittest.TestCase):

    def test_packet_error_probability(self):
        """Validates bit error probability compounding formula."""
        self.assertEqual(packet_error_prob(1000, 0.0), 0.0)
        # 1 bit in 1 byte: P(err) = 1 - (1 - 0.1)^8 = 1 - 0.9^8 ~ 0.5695
        p = packet_error_prob(1, 0.1)
        expected_p = 1.0 - (0.9 ** 8)
        self.assertAlmostEqual(p, expected_p, places=5)

    def test_stop_and_wait_hand_calculated_baseline(self):
        """
        Validates Stop-and-Wait against hand-calculated analytical equations:
        Bandwidth: 10 Mbps = 10,000,000 bps
        Propagation delay: 10 ms = 0.010 s (one way)
        Payload: 1024 bytes
        Header: 40 bytes
        ACK: 40 bytes
        BER: 0.0 (Clean link)
        """
        bw = 10e6
        prop = 0.010
        payload = 1024
        header = 40
        ack = 40

        # Exact hand calculations:
        tx_data = (payload + header) * 8.0 / bw     # 1064 * 8 / 1e7 = 0.0008512 s
        tx_ack = ack * 8.0 / bw                     # 40 * 8 / 1e7   = 0.0000320 s
        ideal_rtt = tx_data + 2.0 * prop + tx_ack  # 0.0208832 s
        expected_goodput_mbps = (payload * 8.0 / ideal_rtt) / 1e6  # ~0.392277 Mbps
        expected_efficiency = payload / (payload + header)         # 1024 / 1064 ~ 0.9624

        cfg = LinkConfig(
            bandwidth_bps=bw,
            prop_delay_s=prop,
            ber=0.0,
            header_bytes=header,
            ack_bytes=ack,
            protocol="stop_and_wait",
            window_size=1,
            enable_fragmentation=False,
            queue_capacity=0
        )

        total_bytes = 1024 * 20  # exactly 20 packets
        rng = random.Random(42)
        res = simulate_transfer(total_bytes, payload, cfg, rng)

        self.assertEqual(res["packets"], 20)
        self.assertAlmostEqual(res["efficiency"], expected_efficiency, places=3)
        # Verify simulated goodput is within 1% of analytical prediction
        self.assertAlmostEqual(res["goodput_mbps"], expected_goodput_mbps, delta=0.01)
        # Verify latency per packet matches ideal RTT
        self.assertAlmostEqual(res["avg_latency_ms"], ideal_rtt * 1000.0, delta=0.5)

    def test_go_back_n_pipelining(self):
        """Validates that Go-Back-N sliding window achieves higher goodput than Stop-and-Wait."""
        cfg_sw = LinkConfig(
            bandwidth_bps=10e6,
            prop_delay_s=0.010,
            ber=0.0,
            protocol="stop_and_wait",
            window_size=1
        )
        cfg_gbn = LinkConfig(
            bandwidth_bps=10e6,
            prop_delay_s=0.010,
            ber=0.0,
            protocol="go_back_n",
            window_size=8
        )

        total_bytes = 100_000
        res_sw = simulate_transfer(total_bytes, 1024, cfg_sw, random.Random(42))
        res_gbn = simulate_transfer(total_bytes, 1024, cfg_gbn, random.Random(42))

        # GBN with window 8 should be significantly faster than Stop-and-Wait
        self.assertGreater(res_gbn["goodput_mbps"], res_sw["goodput_mbps"] * 1.8)
        self.assertLess(res_gbn["total_time_s"], res_sw["total_time_s"])

    def test_selective_repeat_resilience(self):
        """Validates Selective Repeat under loss: out-of-order packets are buffered and not re-sent."""
        cfg_gbn = LinkConfig(
            bandwidth_bps=10e6,
            prop_delay_s=0.010,
            ber=5e-5,
            protocol="go_back_n",
            window_size=8
        )
        cfg_sr = LinkConfig(
            bandwidth_bps=10e6,
            prop_delay_s=0.010,
            ber=5e-5,
            protocol="selective_repeat",
            window_size=8
        )

        total_bytes = 100_000
        res_gbn = simulate_transfer(total_bytes, 1024, cfg_gbn, random.Random(42))
        res_sr = simulate_transfer(total_bytes, 1024, cfg_sr, random.Random(42))

        # Under BER with window > 1, SR should retransmit fewer packets than GBN
        self.assertLessEqual(res_sr["retx_per_packet"], res_gbn["retx_per_packet"])
        self.assertGreaterEqual(res_sr["goodput_mbps"], res_gbn["goodput_mbps"])

    def test_mtu_fragmentation_behavior(self):
        """
        Validates Phase B requirement:
        Sizes above 1500 B MTU are fragmented into multiple packets.
        One lost fragment forces the entire packet to be retransmitted.
        """
        cfg_frag = LinkConfig(
            bandwidth_bps=10e6,
            prop_delay_s=0.010,
            ber=1e-4,  # Moderate noise to demonstrate fragmentation penalty
            mtu_bytes=1500,
            enable_fragmentation=True
        )

        # 1024 B payload: fits in 1 fragment (1024 + 40 <= 1500)
        res_small = simulate_transfer(50_000, 1024, cfg_frag, random.Random(42))
        # 4096 B payload: requires 3 fragments (1460 + 1460 + 1176) per packet
        res_large = simulate_transfer(50_000, 4096, cfg_frag, random.Random(42))

        # Check that large packets generate significantly more fragments than small packets
        frags_per_pkt_small = res_small["fragments_created"] / res_small["packets"]
        frags_per_pkt_large = res_large["fragments_created"] / res_large["packets"]

        self.assertAlmostEqual(frags_per_pkt_small, 1.0, delta=0.5)
        self.assertGreater(frags_per_pkt_large, 2.5)
        # Fragmentation overhead and compounding error probability reduce goodput
        self.assertGreater(res_small["goodput_mbps"], res_large["goodput_mbps"])

    def test_queue_buffering_and_drops(self):
        """Validates router queue buffer overflow drop tracking and queuing delay."""
        cfg = LinkConfig(
            bandwidth_bps=10e6,
            prop_delay_s=0.010,
            protocol="go_back_n",
            window_size=32,
            queue_capacity=5,  # Very small queue
            n_flows=2          # Competing flows
        )

        res = simulate_transfer(50_000, 1024, cfg, random.Random(42))
        # Drops must have occurred due to buffer overflow
        self.assertGreater(res["queue_drops"], 0)
        # Queuing delay must be positive
        self.assertGreater(res["avg_queuing_delay_ms"], 0.0)

    def test_theoretical_optimal_size_finder(self):
        """Validates that theoretical optimal size matches physical intuition and empirical search."""
        # Clean link: optimum is largest packet (minimizes header overhead)
        opt_clean = calculate_theoretical_optimal(0.0, 40)
        self.assertEqual(opt_clean, 8192.0)

        # High BER (1e-4): L* ~ 1192 - 1250 B
        opt_noisy = calculate_theoretical_optimal(1e-4, 40)
        self.assertTrue(1100.0 <= opt_noisy <= 1300.0, f"Expected L* around 1200 B, got {opt_noisy}")

        # Extreme BER (5e-4): L* ~ 256 B
        opt_extreme = calculate_theoretical_optimal(5e-4, 40)
        self.assertTrue(200.0 <= opt_extreme <= 320.0, f"Expected L* around 256 B, got {opt_extreme}")

        # Run empirical finder at BER = 1e-4
        cfg = LinkConfig(ber=1e-4)
        search_res = find_optimal_packet_size(cfg, [64, 128, 256, 512, 1024, 2048, 4096], trials=5, seed=42)
        self.assertEqual(search_res["best_size"], 1024)


if __name__ == "__main__":
    unittest.main()

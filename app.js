/**
 * PULSE · DCN Packet Size & Throughput Optimization Simulator
 * Core JavaScript Engine: Real-time Stop-and-Wait ARQ Visualizer,
 * High-Precision Stochastic Network Simulator, Interactive Charts & Python Bridge.
 */

// =============================================================================
// 1. CONFIGURATION & STATE
// =============================================================================

const BER_SCALE = [0.0, 1e-6, 1e-5, 5e-5, 1e-4, 5e-4, 1e-3];
const BER_LABELS = ["0.0 (Clean)", "1.0 × 10⁻⁶", "1.0 × 10⁻⁵", "5.0 × 10⁻⁵", "1.0 × 10⁻⁴", "5.0 × 10⁻⁴", "1.0 × 10⁻³"];
const BER_DESCRIPTIONS = [
  "Ideal clean fiber/optical link. P(error) = 0.",
  "High-quality fiber/coaxial network. ~1 error per 1M bits.",
  "Standard wireless / 4G cellular channel. 1 error per 100k bits.",
  "Challenged wireless / noisy channel. 1 error per 20k bits.",
  "Harsh industrial RF interference. 1 error per 10k bits.",
  "Severely degraded channel. 1 error per 2k bits.",
  "Extreme noise threshold. Frequent packet loss."
];

const PACKET_SIZES = [64, 128, 256, 512, 1024, 1500, 2048, 4096, 8192];

const PRESETS = {
  baseline: { bandwidth: 10, delay: 10, berIdx: 0, payload: 1024 },
  lan: { bandwidth: 100, delay: 1, berIdx: 0, payload: 1500 },
  wireless: { bandwidth: 20, delay: 25, berIdx: 1, payload: 1500 },
  noisy: { bandwidth: 10, delay: 20, berIdx: 2, payload: 512 },
  satellite: { bandwidth: 10, delay: 250, berIdx: 3, payload: 2048 }
};

const state = {
  // Config
  bandwidthMbps: 10.0,
  propDelayMs: 10.0,
  berIndex: 0,
  payloadBytes: 1024,
  headerBytes: 40,
  ackBytes: 40,
  timeoutMarginMs: 5.0,
  totalBytesKB: 500,
  maxRetries: 100,

  // Runtime State
  activeTab: 'visualizer',
  isBackendOnline: false,
  
  // Visualizer Runtime
  simRunning: false,
  simPaused: false,
  simSpeed: 1.0,
  forceCorruptNext: false,
  currentSeq: 0,
  currentAttempts: 0,
  deliveredBytes: 0,
  totalPackets: 0,
  clockSeconds: 0.0,
  liveLog: [],
  eventFeed: [],

  // Inspector & Pagination
  inspectorFilter: 'all',
  inspectorQuery: '',
  currentPage: 1,
  pageSize: 50,

  // Sweeps Data
  sweepData: null
};

// =============================================================================
// 2. MATHEMATICAL & STOCHASTIC SIMULATION CORE
// =============================================================================

function packetErrorProb(sizeBytes, ber) {
  if (ber <= 0) return 0.0;
  return 1.0 - Math.pow(1.0 - ber, 8.0 * sizeBytes);
}

function computeLinkConfig() {
  const ber = BER_SCALE[state.berIndex];
  return {
    bandwidthBps: state.bandwidthMbps * 1e6,
    propDelayS: state.propDelayMs / 1000.0,
    ber: ber,
    headerBytes: state.headerBytes,
    ackBytes: state.ackBytes,
    timeoutMarginS: state.timeoutMarginMs / 1000.0,
    maxRetries: state.maxRetries,
    payloadBytes: state.payloadBytes,
    totalBytes: state.totalBytesKB * 1000
  };
}

/**
 * Fast client-side Monte-Carlo simulation matching packet_sim.py exactly
 */
function runTransferSimulation(totalBytes, payloadBytes, cfg, seed = 42, collectLog = true) {
  const nPackets = Math.ceil(totalBytes / payloadBytes);
  let clock = 0.0;
  let deliveredPayload = 0;
  let wireBytesOk = 0;
  let totalTx = 0;
  let failedPackets = 0;
  const latencies = [];
  const log = [];

  const ackTxTime = (cfg.ackBytes * 8) / cfg.bandwidthBps;
  const pAckErr = packetErrorProb(cfg.ackBytes, cfg.ber);

  // Deterministic seeded pseudo-RNG for reproducibility
  let rngSeed = seed;
  function random() {
    rngSeed = (rngSeed * 9301 + 49297) % 233280;
    return rngSeed / 233280;
  }

  for (let seq = 0; seq < nPackets; seq++) {
    const thisPayload = Math.min(payloadBytes, totalBytes - seq * payloadBytes);
    const frame = thisPayload + cfg.headerBytes;
    const txTime = (frame * 8) / cfg.bandwidthBps;
    const pErr = packetErrorProb(frame, cfg.ber);
    const idealRtt = txTime + 2 * cfg.propDelayS + ackTxTime;
    const timeout = idealRtt + cfg.timeoutMarginS;

    const tFirstSend = clock;
    let attempts = 0;
    let success = false;

    while (attempts < cfg.maxRetries) {
      attempts++;
      totalTx++;
      const dataOk = random() >= pErr;
      const ackOk = dataOk && (random() >= pAckErr);
      if (ackOk) {
        clock += idealRtt;
        success = true;
        break;
      }
      clock += timeout;
    }

    const latency = clock - tFirstSend;
    if (success) {
      deliveredPayload += thisPayload;
      wireBytesOk += frame;
      latencies.push(latency);
    } else {
      failedPackets += 1;
    }

    if (collectLog && (seq < 2000)) {
      log.push({
        seq,
        payload: thisPayload,
        wire: frame,
        attempts,
        success,
        start_s: tFirstSend,
        end_s: clock,
        latency_s: latency
      });
    }
  }

  const totalTime = clock > 0 ? clock : 1e-12;
  const sumLatency = latencies.reduce((a, b) => a + b, 0);
  const avgLatencyMs = latencies.length ? (1000 * sumLatency) / latencies.length : 0;
  
  // Percentile 95
  latencies.sort((a, b) => a - b);
  const p95Idx = Math.floor(latencies.length * 0.95);
  const p95LatencyMs = latencies.length ? 1000 * latencies[p95Idx] : 0;

  return {
    packets: nPackets,
    totalTimeS: totalTime,
    throughputMbps: (wireBytesOk * 8) / totalTime / 1e6,
    goodputMbps: (deliveredPayload * 8) / totalTime / 1e6,
    avgLatencyMs: avgLatencyMs,
    p95LatencyMs: p95LatencyMs,
    retxPerPacket: (totalTx - nPackets) / nPackets,
    lossPct: (100 * failedPackets) / nPackets,
    efficiency: payloadBytes / (payloadBytes + cfg.headerBytes),
    log: log
  };
}

/**
 * Analytical Goodput Calculator for immediate responsive curve rendering
 */
function theoreticalGoodput(payloadBytes, cfg) {
  const frameBytes = payloadBytes + cfg.headerBytes;
  const pErr = packetErrorProb(frameBytes, cfg.ber);
  const pAckErr = packetErrorProb(cfg.ackBytes, cfg.ber);
  const pFrameLoss = 1.0 - (1.0 - pErr) * (1.0 - pAckErr);

  const txTime = (frameBytes * 8) / cfg.bandwidthBps;
  const ackTxTime = (cfg.ackBytes * 8) / cfg.bandwidthBps;
  const idealRtt = txTime + 2 * cfg.propDelayS + ackTxTime;
  const timeout = idealRtt + cfg.timeoutMarginS;

  // Expected attempts = 1 / (1 - pFrameLoss)
  // Expected time per packet = idealRtt + (E[attempts] - 1) * timeout
  const probSuccess = 1.0 - pFrameLoss;
  if (probSuccess <= 1e-6) return 0.0;
  
  const expectedTime = idealRtt + (pFrameLoss / probSuccess) * timeout;
  const goodputBps = (payloadBytes * 8) / expectedTime;
  return goodputBps / 1e6;
}

/**
 * Finds optimal packet size L* that maximizes Goodput
 */
function findOptimalPacketSize(cfg) {
  let bestSize = 64;
  let maxGp = -1;
  for (let s = 64; s <= 8192; s += 64) {
    const gp = theoreticalGoodput(s, cfg);
    if (gp > maxGp) {
      maxGp = gp;
      bestSize = s;
    }
  }
  return { size: bestSize, goodput: maxGp };
}

// =============================================================================
// 3. UI CONTROLS & BINDINGS
// =============================================================================

function setupEventListeners() {
  // Soft UI Theme Toggle
  const themeBtn = document.getElementById('btnThemeToggle');
  if (themeBtn) {
    const savedTheme = localStorage.getItem('pulse_theme');
    if (savedTheme === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
    }
    themeBtn.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme');
      const newTheme = current === 'dark' ? 'light' : 'dark';
      if (newTheme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('pulse_theme', 'dark');
        showNotification('Switched to Dark Neumorphism (Soft Slate)');
      } else {
        document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('pulse_theme', 'light');
        showNotification('Switched to Classic Neumorphism (Soft Gray #e0e5ec)');
      }
      updateChartsTheme();
    });
  }

  // Range sliders
  const elBw = document.getElementById('cfgBandwidth');
  const elDelay = document.getElementById('cfgDelay');
  const elBer = document.getElementById('cfgBer');
  const elPayload = document.getElementById('cfgPayload');

  elBw.addEventListener('input', (e) => {
    state.bandwidthMbps = parseFloat(e.target.value);
    document.getElementById('lblBandwidth').textContent = `${state.bandwidthMbps.toFixed(1)} Mbps`;
    updateSimulationCalculations();
  });

  elDelay.addEventListener('input', (e) => {
    state.propDelayMs = parseFloat(e.target.value);
    document.getElementById('lblDelay').textContent = `${state.propDelayMs.toFixed(1)} ms`;
    updateSimulationCalculations();
  });

  elBer.addEventListener('input', (e) => {
    state.berIndex = parseInt(e.target.value, 10);
    document.getElementById('lblBer').textContent = BER_LABELS[state.berIndex];
    document.getElementById('berExplanation').textContent = BER_DESCRIPTIONS[state.berIndex];
    updateSimulationCalculations();
  });

  elPayload.addEventListener('input', (e) => {
    state.payloadBytes = parseInt(e.target.value, 10);
    document.getElementById('lblPayload').textContent = `${state.payloadBytes} B`;
    highlightPayloadChip(state.payloadBytes);
    updateSimulationCalculations();
  });

  // Payload chips
  const chips = document.querySelectorAll('#payloadChips .chip');
  chips.forEach((chip) => {
    chip.addEventListener('click', () => {
      const size = parseInt(chip.dataset.size, 10);
      state.payloadBytes = size;
      elPayload.value = size;
      document.getElementById('lblPayload').textContent = `${size} B`;
      highlightPayloadChip(size);
      updateSimulationCalculations();
    });
  });

  // Preset buttons
  const presetButtons = document.querySelectorAll('#presetPills .preset-btn');
  presetButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      presetButtons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      applyPreset(btn.dataset.preset);
    });
  });

  // Apply Optimal button
  document.getElementById('btnApplyOptimum').addEventListener('click', () => {
    const cfg = computeLinkConfig();
    const opt = findOptimalPacketSize(cfg);
    state.payloadBytes = opt.size;
    elPayload.value = opt.size;
    document.getElementById('lblPayload').textContent = `${opt.size} B`;
    highlightPayloadChip(opt.size);
    updateSimulationCalculations();
  });

  // Advanced Inputs
  document.getElementById('cfgHeader').addEventListener('change', (e) => {
    state.headerBytes = parseInt(e.target.value, 10) || 40;
    updateSimulationCalculations();
  });
  document.getElementById('cfgAck').addEventListener('change', (e) => {
    state.ackBytes = parseInt(e.target.value, 10) || 40;
    updateSimulationCalculations();
  });
  document.getElementById('cfgTimeoutMargin').addEventListener('change', (e) => {
    state.timeoutMarginMs = parseFloat(e.target.value) || 5.0;
    updateSimulationCalculations();
  });
  document.getElementById('cfgTotalBytes').addEventListener('change', (e) => {
    state.totalBytesKB = parseInt(e.target.value, 10) || 500;
    updateSimulationCalculations();
  });
  document.getElementById('cfgMaxRetries').addEventListener('change', (e) => {
    state.maxRetries = parseInt(e.target.value, 10) || 100;
  });

  // Reset Button
  document.getElementById('btnResetConfig').addEventListener('click', () => {
    applyPreset('baseline');
  });

  // Top Nav Actions
  document.getElementById('btnRunSim').addEventListener('click', () => {
    switchTab('visualizer');
    startVisualizerTransfer();
  });

  document.getElementById('btnRunSweep').addEventListener('click', () => {
    switchTab('analytics');
    computeAndRenderSweeps();
  });

  document.getElementById('btnExportCSV').addEventListener('click', exportLogsToCSV);
  document.getElementById('btnDownloadLogCSV').addEventListener('click', exportLogsToCSV);

  // Tab buttons
  const tabButtons = document.querySelectorAll('.content-tabs .tab-btn');
  tabButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      switchTab(btn.dataset.tab);
    });
  });

  // Visualizer Stage Buttons
  document.getElementById('btnSimToggle').addEventListener('click', toggleVisualizerFlow);
  document.getElementById('btnSimStep').addEventListener('click', stepVisualizerPacket);
  document.getElementById('btnSimReset').addEventListener('click', resetVisualizer);
  document.getElementById('btnCorruptNext').addEventListener('click', () => {
    state.forceCorruptNext = true;
    showNotification('Next packet transmission will be manually corrupted! ⚡');
  });

  document.getElementById('animSpeed').addEventListener('change', (e) => {
    state.simSpeed = parseFloat(e.target.value);
  });

  // Analytics toolbar
  document.getElementById('btnComputeSweep').addEventListener('click', computeAndRenderSweeps);
  document.getElementById('btnLoadPythonCsv').addEventListener('click', loadPythonSummaryCsv);

  // Python tab
  document.getElementById('btnExecutePythonScript').addEventListener('click', executePythonBackend);

  // Inspector filters
  const filterPills = document.querySelectorAll('#inspectorFilterPills .filter-pill');
  filterPills.forEach((pill) => {
    pill.addEventListener('click', () => {
      filterPills.forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      state.inspectorFilter = pill.dataset.filter;
      state.currentPage = 1;
      renderInspectorTable();
    });
  });

  document.getElementById('inspectorSearch').addEventListener('input', (e) => {
    state.inspectorQuery = e.target.value.toLowerCase();
    state.currentPage = 1;
    renderInspectorTable();
  });

  document.getElementById('btnPrevPage').addEventListener('click', () => {
    if (state.currentPage > 1) {
      state.currentPage--;
      renderInspectorTable();
    }
  });

  document.getElementById('btnNextPage').addEventListener('click', () => {
    state.currentPage++;
    renderInspectorTable();
  });
}

function highlightPayloadChip(size) {
  const chips = document.querySelectorAll('#payloadChips .chip');
  chips.forEach(c => {
    if (parseInt(c.dataset.size, 10) === size) {
      c.classList.add('active');
    } else {
      c.classList.remove('active');
    }
  });
}

function applyPreset(name) {
  const p = PRESETS[name] || PRESETS.baseline;
  state.bandwidthMbps = p.bandwidth;
  state.propDelayMs = p.delay;
  state.berIndex = p.berIdx;
  state.payloadBytes = p.payload;

  document.getElementById('cfgBandwidth').value = p.bandwidth;
  document.getElementById('lblBandwidth').textContent = `${p.bandwidth.toFixed(1)} Mbps`;

  document.getElementById('cfgDelay').value = p.delay;
  document.getElementById('lblDelay').textContent = `${p.delay.toFixed(1)} ms`;

  document.getElementById('cfgBer').value = p.berIdx;
  document.getElementById('lblBer').textContent = BER_LABELS[p.berIdx];
  document.getElementById('berExplanation').textContent = BER_DESCRIPTIONS[p.berIdx];

  document.getElementById('cfgPayload').value = p.payload;
  document.getElementById('lblPayload').textContent = `${p.payload} B`;
  highlightPayloadChip(p.payload);

  updateSimulationCalculations();
}

function switchTab(tabId) {
  state.activeTab = tabId;
  document.querySelectorAll('.content-tabs .tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabId);
  });
  document.querySelectorAll('.tab-pane').forEach(pane => {
    pane.classList.remove('active');
  });

  const targetPane = document.getElementById(`pane${capitalize(tabId)}`);
  if (targetPane) {
    targetPane.classList.add('active');
  }

  if (tabId === 'analytics') {
    if (!chartsInitialized) {
      initCharts();
      computeAndRenderSweeps();
    }
  } else if (tabId === 'inspector') {
    renderInspectorTable();
  }
}

function capitalize(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// =============================================================================
// 4. METRICS & RECALCULATION
// =============================================================================

function updateSimulationCalculations() {
  const cfg = computeLinkConfig();
  const opt = findOptimalPacketSize(cfg);

  // Update advisor box
  document.getElementById('optPayloadVal').textContent = `${opt.size} B`;
  document.getElementById('optPayloadDesc').textContent = `Max theoretical goodput: ${opt.goodput.toFixed(3)} Mbps`;

  // Calculate instant theoretical values
  const frameBytes = state.payloadBytes + state.headerBytes;
  const pErr = packetErrorProb(frameBytes, cfg.ber);
  const gp = theoreticalGoodput(state.payloadBytes, cfg);
  const eff = state.payloadBytes / frameBytes;
  const tp = gp / eff;

  const txTimeMs = ((frameBytes * 8) / cfg.bandwidthBps) * 1000;
  const ackTimeMs = ((cfg.ackBytes * 8) / cfg.bandwidthBps) * 1000;
  const idealRttMs = txTimeMs + 2 * state.propDelayMs + ackTimeMs;
  const expectedRetx = pErr > 0 ? pErr / (1.0 - pErr) : 0.0;
  const avgLatencyMs = idealRttMs + expectedRetx * (idealRttMs + state.timeoutMarginMs);

  // Update KPI Cards
  document.getElementById('valGoodput').textContent = gp.toFixed(3);
  document.getElementById('subGoodputEff').textContent = `Efficiency: ${(eff * 100).toFixed(1)}%`;

  document.getElementById('valThroughput').textContent = tp.toFixed(3);
  document.getElementById('subThroughputOverhead').textContent = `Includes ${state.headerBytes}B Header`;

  document.getElementById('valLatency').textContent = avgLatencyMs.toFixed(2);
  document.getElementById('subP95Latency').textContent = `Ideal RTT: ${idealRttMs.toFixed(2)} ms`;

  document.getElementById('valRetx').textContent = expectedRetx.toFixed(2);
  document.getElementById('subLossRate').textContent = `Loss: ${(pErr * 100).toFixed(2)}%`;

  document.getElementById('valPerr').textContent = (pErr * 100).toFixed(2);
  document.getElementById('subPerrFormula').textContent = `1 - (1 - BER)⁸ᶠ`;

  // Update Theory Calculator pane
  document.getElementById('calcPayloadDisp').textContent = `${state.payloadBytes} B`;
  document.getElementById('calcFrameDisp').textContent = `${frameBytes} B (${(frameBytes * 8).toLocaleString()} bits)`;
  document.getElementById('calcBerDisp').textContent = cfg.ber.toExponential(1);
  document.getElementById('calcPerrDisp').textContent = `${(pErr * 100).toFixed(4)}%`;
  document.getElementById('calcExpTxDisp').textContent = (1.0 + expectedRetx).toFixed(3);
  document.getElementById('calcGoodputDisp').textContent = `${gp.toFixed(3)} Mbps`;

  // Update Channel noise label in visualizer
  const noiseLabel = document.getElementById('noiseFieldLabel');
  if (noiseLabel) {
    noiseLabel.textContent = `Channel Medium · ${state.bandwidthMbps} Mbps · ${state.propDelayMs} ms Delay · BER: ${cfg.ber.toExponential(1)}`;
  }
}

// =============================================================================
// 5. REAL-TIME ARQ VISUALIZER
// =============================================================================

let animFrameId = null;
let currentAnimStep = null;

function resetVisualizer() {
  state.simRunning = false;
  state.simPaused = false;
  state.currentSeq = 0;
  state.currentAttempts = 1;
  state.deliveredBytes = 0;
  state.clockSeconds = 0.0;
  state.liveLog = [];
  state.eventFeed = [];

  const cfg = computeLinkConfig();
  state.totalPackets = Math.ceil(cfg.totalBytes / state.payloadBytes);

  document.getElementById('btnSimToggle').textContent = 'Start Flow';
  document.getElementById('simStateBadge').textContent = 'IDLE';
  document.getElementById('simStateBadge').className = 'stage-status-badge';

  document.getElementById('teleSenderSeq').textContent = '0';
  document.getElementById('teleSenderAttempt').textContent = '1';
  document.getElementById('teleSenderQueue').textContent = `${state.totalPackets} pkts`;

  document.getElementById('teleRxCount').textContent = '0';
  document.getElementById('teleRxCRC').textContent = 'READY';
  document.getElementById('teleRxBytes').textContent = '0 KB';
  document.getElementById('rxStatusPill').textContent = 'Ready';

  document.getElementById('progressPercent').textContent = '0%';
  document.getElementById('progressBytes').textContent = '0';
  document.getElementById('progressTotal').textContent = `${state.totalBytesKB} KB`;
  document.getElementById('progressPktsDone').textContent = '0';
  document.getElementById('progressPktsTotal').textContent = `${state.totalPackets}`;
  document.getElementById('progressFill').style.width = '0%';

  document.getElementById('packetCapsule').style.display = 'none';
  document.getElementById('ackCapsule').style.display = 'none';
  document.getElementById('errorFlashOverlay').style.display = 'none';

  document.getElementById('timerDialBar').style.setProperty('--timer-progress', '0%');
  document.getElementById('timerDialText').textContent = 'Timer Idle';

  document.getElementById('eventFeedStream').innerHTML = '<div class="event-feed-empty">Ready to transmit. Click "Start Flow" or "Step" above.</div>';
  document.getElementById('feedCount').textContent = '0 events';

  if (animFrameId) {
    cancelAnimationFrame(animFrameId);
    animFrameId = null;
  }
}

function toggleVisualizerFlow() {
  if (state.simRunning) {
    state.simRunning = false;
    document.getElementById('btnSimToggle').textContent = 'Resume Flow';
    document.getElementById('simStateBadge').textContent = 'PAUSED';
  } else {
    state.simRunning = true;
    document.getElementById('btnSimToggle').textContent = 'Pause Flow';
    if (state.currentSeq >= state.totalPackets) {
      resetVisualizer();
      state.simRunning = true;
      document.getElementById('btnSimToggle').textContent = 'Pause Flow';
    }
    runVisualizerLoop();
  }
}

function startVisualizerTransfer() {
  resetVisualizer();
  state.simRunning = true;
  document.getElementById('btnSimToggle').textContent = 'Pause Flow';
  runVisualizerLoop();
}

function stepVisualizerPacket() {
  state.simRunning = false;
  document.getElementById('btnSimToggle').textContent = 'Resume Flow';
  executeOnePacketStep();
}

function appendEventFeed(type, msg) {
  const stream = document.getElementById('eventFeedStream');
  const empty = stream.querySelector('.event-feed-empty');
  if (empty) empty.remove();

  const timeStr = `+${state.clockSeconds.toFixed(3)}s`;
  const row = document.createElement('div');
  row.className = `feed-row ${type}`;
  row.innerHTML = `<span class="feed-time">${timeStr}</span> <span class="feed-msg">${msg}</span>`;
  stream.prepend(row);

  state.eventFeed.unshift({ type, msg, time: state.clockSeconds });
  document.getElementById('feedCount').textContent = `${state.eventFeed.length} events`;
}

/**
 * Executes a single packet flow in the visualizer with smooth CSS/requestAnimationFrame animation
 */
async function executeOnePacketStep() {
  if (state.currentSeq >= state.totalPackets) {
    state.simRunning = false;
    document.getElementById('btnSimToggle').textContent = 'Transfer Complete';
    document.getElementById('simStateBadge').textContent = 'COMPLETED';
    document.getElementById('simStateBadge').className = 'stage-status-badge ack-ok';
    appendEventFeed('ack', `🎉 Transfer finished! Successfully delivered ${state.deliveredBytes.toLocaleString()} bytes.`);
    renderInspectorTable();
    return false;
  }

  const cfg = computeLinkConfig();
  const thisPayload = Math.min(state.payloadBytes, cfg.totalBytes - state.currentSeq * state.payloadBytes);
  const frameBytes = thisPayload + cfg.headerBytes;

  const txTimeS = (frameBytes * 8) / cfg.bandwidthBps;
  const ackTxTimeS = (cfg.ackBytes * 8) / cfg.bandwidthBps;
  const idealRttS = txTimeS + 2 * cfg.propDelayS + ackTxTimeS;
  const timeoutS = idealRttS + cfg.timeoutMarginS;

  // Determine Bit Error corruptions
  const pErr = packetErrorProb(frameBytes, cfg.ber);
  const pAckErr = packetErrorProb(cfg.ackBytes, cfg.ber);
  
  let isCorrupted = Math.random() < pErr;
  if (state.forceCorruptNext) {
    isCorrupted = true;
    state.forceCorruptNext = false;
  }
  const isAckCorrupted = !isCorrupted && (Math.random() < pAckErr);

  // Speed-adjusted animation duration
  const baseDurationMs = state.simSpeed >= 999 ? 0 : Math.max(80, 800 / state.simSpeed);

  // 1. SENDER: Transmit packet
  document.getElementById('simStateBadge').textContent = `TX #${state.currentSeq}`;
  document.getElementById('simStateBadge').className = 'stage-status-badge transmitting';
  document.getElementById('nodeSender').classList.add('active-tx');
  document.getElementById('teleSenderSeq').textContent = `${state.currentSeq}`;
  document.getElementById('teleSenderAttempt').textContent = `${state.currentAttempts}`;
  document.getElementById('teleSenderQueue').textContent = `${state.totalPackets - state.currentSeq} pkts`;

  appendEventFeed('tx', `Sender dispatching packet #${state.currentSeq} (${thisPayload}B payload, attempt ${state.currentAttempts})...`);

  // Animate Forward Packet Traveling
  const packetEl = document.getElementById('packetCapsule');
  packetEl.style.display = 'flex';
  packetEl.className = `packet-capsule ${isCorrupted ? 'corrupted' : ''}`;
  document.getElementById('capsulePayloadText').textContent = `P:${thisPayload}B`;
  document.getElementById('capsuleSeqBadge').textContent = `#${state.currentSeq}`;

  if (baseDurationMs > 0) {
    await animateElementPosition(packetEl, '--packet-pos', 5, 95, baseDurationMs);
  }

  document.getElementById('nodeSender').classList.remove('active-tx');

  if (isCorrupted) {
    // Corrupted in transit
    document.getElementById('errorFlashOverlay').style.display = 'block';
    document.getElementById('simStateBadge').textContent = 'ERROR DETECTED';
    document.getElementById('simStateBadge').className = 'stage-status-badge corrupted';
    document.getElementById('teleRxCRC').textContent = 'FAIL (CORRUPTED)';
    document.getElementById('teleRxCRC').className = 'mono text-rose';
    document.getElementById('rxStatusPill').textContent = 'CRC Mismatch - Dropped';

    appendEventFeed('corrupt', `⚡ Bit error occurred in transmission! Frame #${state.currentSeq} corrupted. Receiver dropped frame.`);

    // Timeout wait
    if (baseDurationMs > 0) {
      await animateTimeoutTimer(baseDurationMs * 0.8);
    }

    state.clockSeconds += timeoutS;
    state.currentAttempts++;
    document.getElementById('errorFlashOverlay').style.display = 'none';
    packetEl.style.display = 'none';

    // Log the failed attempt
    state.liveLog.push({
      seq: state.currentSeq,
      payload: thisPayload,
      wire: frameBytes,
      attempts: state.currentAttempts,
      success: false,
      start_s: state.clockSeconds - timeoutS,
      end_s: state.clockSeconds,
      latency_s: timeoutS
    });

    return true;
  }

  // Receiver receives frame
  document.getElementById('nodeReceiver').classList.add('active-rx');
  document.getElementById('teleRxCRC').textContent = 'PASS';
  document.getElementById('teleRxCRC').className = 'mono text-green';
  document.getElementById('rxStatusPill').textContent = `Frame #${state.currentSeq} Verified`;
  packetEl.style.display = 'none';

  // 2. RECEIVER sends ACK
  const ackEl = document.getElementById('ackCapsule');
  ackEl.style.display = 'flex';
  document.getElementById('ackCapsuleText').textContent = `ACK #${state.currentSeq}`;

  if (baseDurationMs > 0) {
    await animateElementPosition(ackEl, '--ack-pos', 5, 95, baseDurationMs * 0.7);
  }

  document.getElementById('nodeReceiver').classList.remove('active-rx');

  if (isAckCorrupted) {
    appendEventFeed('corrupt', `⚠️ ACK #${state.currentSeq} corrupted on return link! Sender timeout.`);
    ackEl.style.display = 'none';
    state.clockSeconds += timeoutS;
    state.currentAttempts++;
    return true;
  }

  // 3. ACK Arrives successfully
  ackEl.style.display = 'none';
  document.getElementById('simStateBadge').textContent = `ACK #${state.currentSeq} OK`;
  document.getElementById('simStateBadge').className = 'stage-status-badge ack-ok';

  state.clockSeconds += idealRttS;
  state.deliveredBytes += thisPayload;

  // Log successful frame
  state.liveLog.push({
    seq: state.currentSeq,
    payload: thisPayload,
    wire: frameBytes,
    attempts: state.currentAttempts,
    success: true,
    start_s: state.clockSeconds - idealRttS,
    end_s: state.clockSeconds,
    latency_s: idealRttS
  });

  appendEventFeed('ack', `✓ ACK #${state.currentSeq} received! RTT: ${(idealRttS * 1000).toFixed(2)} ms.`);

  // Progress Update
  state.currentSeq++;
  state.currentAttempts = 1;

  const pct = Math.min(100, (state.deliveredBytes / cfg.totalBytes) * 100);
  document.getElementById('progressPercent').textContent = `${pct.toFixed(1)}%`;
  document.getElementById('progressBytes').textContent = `${Math.round(state.deliveredBytes / 1000)} KB`;
  document.getElementById('progressPktsDone').textContent = `${state.currentSeq}`;
  document.getElementById('progressFill').style.width = `${pct}%`;

  document.getElementById('teleRxCount').textContent = `${state.currentSeq}`;
  document.getElementById('teleRxBytes').textContent = `${(state.deliveredBytes / 1000).toFixed(1)} KB`;

  return true;
}

function animateElementPosition(el, cssVar, fromVal, toVal, durationMs) {
  return new Promise((resolve) => {
    const startTime = performance.now();
    function tick(now) {
      const elapsed = now - startTime;
      const progress = Math.min(1, elapsed / durationMs);
      const current = fromVal + (toVal - fromVal) * progress;
      el.style.setProperty(cssVar, `${current}%`);
      if (progress < 1) {
        requestAnimationFrame(tick);
      } else {
        resolve();
      }
    }
    requestAnimationFrame(tick);
  });
}

function animateTimeoutTimer(durationMs) {
  return new Promise((resolve) => {
    const bar = document.getElementById('timerDialBar');
    const text = document.getElementById('timerDialText');
    text.textContent = 'Waiting ACK...';
    const startTime = performance.now();
    function tick(now) {
      const elapsed = now - startTime;
      const progress = Math.min(1, elapsed / durationMs);
      bar.style.setProperty('--timer-progress', `${progress * 100}%`);
      if (progress < 1) {
        requestAnimationFrame(tick);
      } else {
        bar.style.setProperty('--timer-progress', '0%');
        text.textContent = 'Timeout! Retrying...';
        resolve();
      }
    }
    requestAnimationFrame(tick);
  });
}

async function runVisualizerLoop() {
  while (state.simRunning && state.currentSeq < state.totalPackets) {
    const canContinue = await executeOnePacketStep();
    if (!canContinue) break;
  }
}

// =============================================================================
// 6. CHART.JS ANALYTICS & PARAMETER SWEEPS (Phase 3)
// =============================================================================

let chartGoodput = null;
let chartThroughput = null;
let chartLatency = null;
let chartRetx = null;
let chartsInitialized = false;

const CHART_COLORS = [
  { border: '#38bdf8', bg: 'rgba(56, 189, 248, 0.15)', name: 'BER=0' },
  { border: '#10b981', bg: 'rgba(16, 185, 129, 0.15)', name: 'BER=1e-6' },
  { border: '#818cf8', bg: 'rgba(129, 140, 248, 0.15)', name: 'BER=1e-5' },
  { border: '#f59e0b', bg: 'rgba(245, 158, 11, 0.15)', name: 'BER=5e-5' },
  { border: '#f43f5e', bg: 'rgba(244, 63, 94, 0.15)', name: 'BER=1e-4' }
];

function getChartThemeColors() {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  return {
    grid: isDark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(163, 177, 198, 0.35)',
    ticks: isDark ? '#94a3b8' : '#4a5568',
    legend: isDark ? '#cbd5e1' : '#1e293b',
    title: isDark ? '#f8fafc' : '#1e293b',
    tooltipBg: isDark ? '#1e232b' : '#e0e5ec',
    tooltipBorder: isDark ? '#282f3a' : '#a3b1c6',
    tooltipText: isDark ? '#f8fafc' : '#1e293b'
  };
}

function updateChartsTheme() {
  if (!chartsInitialized) return;
  const theme = getChartThemeColors();
  const allCharts = [chartGoodput, chartThroughput, chartLatency, chartRetx];
  allCharts.forEach(c => {
    if (!c) return;
    c.options.scales.x.grid.color = theme.grid;
    c.options.scales.x.ticks.color = theme.ticks;
    c.options.scales.x.title.color = theme.title;
    c.options.scales.y.grid.color = theme.grid;
    c.options.scales.y.ticks.color = theme.ticks;
    c.options.scales.y.title.color = theme.title;
    c.options.plugins.legend.labels.color = theme.legend;
    c.options.plugins.tooltip.backgroundColor = theme.tooltipBg;
    c.options.plugins.tooltip.borderColor = theme.tooltipBorder;
    c.options.plugins.tooltip.titleColor = theme.tooltipText;
    c.options.plugins.tooltip.bodyColor = theme.tooltipText;
    c.update();
  });
}

function initCharts() {
  if (chartsInitialized) return;
  if (typeof Chart === 'undefined') {
    console.warn('Chart.js not loaded yet');
    return;
  }

  const theme = getChartThemeColors();

  const commonOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 500 },
    plugins: {
      legend: {
        labels: {
          color: theme.legend,
          font: { family: 'Plus Jakarta Sans', size: 11, weight: '600' },
          boxWidth: 12
        }
      },
      tooltip: {
        backgroundColor: theme.tooltipBg,
        borderColor: theme.tooltipBorder,
        borderWidth: 1,
        titleColor: theme.tooltipText,
        bodyColor: theme.tooltipText,
        titleFont: { family: 'Plus Jakarta Sans', size: 12, weight: 'bold' },
        bodyFont: { family: 'JetBrains Mono', size: 11 },
        padding: 10,
        boxPadding: 4
      }
    },
    scales: {
      x: {
        grid: { color: theme.grid },
        ticks: { color: theme.ticks, font: { family: 'JetBrains Mono', size: 10, weight: '600' } },
        title: { display: true, text: 'Payload Size (Bytes)', color: theme.title, font: { size: 11, weight: '700' } }
      },
      y: {
        grid: { color: theme.grid },
        ticks: { color: theme.ticks, font: { family: 'JetBrains Mono', size: 10, weight: '600' } }
      }
    }
  };

  // Goodput Chart
  const ctxGp = document.getElementById('chartGoodput').getContext('2d');
  chartGoodput = new Chart(ctxGp, {
    type: 'line',
    data: { labels: PACKET_SIZES.map(s => `${s}B`), datasets: [] },
    options: {
      ...commonOptions,
      scales: {
        ...commonOptions.scales,
        y: { ...commonOptions.scales.y, title: { display: true, text: 'Goodput (Mbps)', color: theme.title, font: { weight: '700' } } }
      }
    }
  });

  // Throughput Chart
  const ctxTp = document.getElementById('chartThroughput').getContext('2d');
  chartThroughput = new Chart(ctxTp, {
    type: 'line',
    data: { labels: PACKET_SIZES.map(s => `${s}B`), datasets: [] },
    options: {
      ...commonOptions,
      scales: {
        ...commonOptions.scales,
        y: { ...commonOptions.scales.y, title: { display: true, text: 'Throughput (Mbps)', color: theme.title, font: { weight: '700' } } }
      }
    }
  });

  // Latency Chart
  const ctxLat = document.getElementById('chartLatency').getContext('2d');
  chartLatency = new Chart(ctxLat, {
    type: 'line',
    data: { labels: PACKET_SIZES.map(s => `${s}B`), datasets: [] },
    options: {
      ...commonOptions,
      scales: {
        ...commonOptions.scales,
        y: { ...commonOptions.scales.y, title: { display: true, text: 'Latency (ms)', color: theme.title, font: { weight: '700' } } }
      }
    }
  });

  // Retransmission Chart
  const ctxRetx = document.getElementById('chartRetx').getContext('2d');
  chartRetx = new Chart(ctxRetx, {
    type: 'line',
    data: { labels: PACKET_SIZES.map(s => `${s}B`), datasets: [] },
    options: {
      ...commonOptions,
      scales: {
        ...commonOptions.scales,
        y: { ...commonOptions.scales.y, title: { display: true, text: 'Retx / Packet', color: theme.title, font: { weight: '700' } } }
      }
    }
  });

  chartsInitialized = true;
}

/**
 * Computes sweeps across all BER values and packet sizes
 */
function computeAndRenderSweeps() {
  initCharts();
  const bers = [0.0, 1e-6, 1e-5, 5e-5, 1e-4];
  const cfgBase = computeLinkConfig();

  const gpDatasets = [];
  const tpDatasets = [];
  const latDatasets = [];
  const retxDatasets = [];
  const matrixData = [];

  bers.forEach((ber, bIdx) => {
    const color = CHART_COLORS[bIdx];
    const gpPoints = [];
    const tpPoints = [];
    const latPoints = [];
    const retxPoints = [];

    let bestSize = 64;
    let maxGp = -1;

    PACKET_SIZES.forEach((size) => {
      const cfg = { ...cfgBase, ber: ber };
      const gp = theoreticalGoodput(size, cfg);
      const frameBytes = size + cfg.headerBytes;
      const pErr = packetErrorProb(frameBytes, ber);
      const eff = size / frameBytes;
      const tp = eff > 0 ? gp / eff : 0;
      
      const txTimeMs = ((frameBytes * 8) / cfg.bandwidthBps) * 1000;
      const idealRttMs = txTimeMs + 2 * state.propDelayMs + (cfg.ackBytes * 8 / cfg.bandwidthBps) * 1000;
      const retx = pErr > 0 ? pErr / (1.0 - pErr) : 0;
      const lat = idealRttMs + retx * (idealRttMs + state.timeoutMarginMs);

      gpPoints.push(parseFloat(gp.toFixed(3)));
      tpPoints.push(parseFloat(tp.toFixed(3)));
      latPoints.push(parseFloat(lat.toFixed(2)));
      retxPoints.push(parseFloat(retx.toFixed(3)));

      if (gp > maxGp) {
        maxGp = gp;
        bestSize = size;
      }
    });

    matrixData.push({ ber, bestSize, maxGp });

    const datasetTemplate = {
      label: `BER=${ber === 0 ? '0' : ber.toExponential(0)}`,
      borderColor: color.border,
      backgroundColor: color.bg,
      borderWidth: 2,
      pointRadius: 4,
      pointHoverRadius: 6,
      tension: 0.3
    };

    gpDatasets.push({ ...datasetTemplate, data: gpPoints });
    tpDatasets.push({ ...datasetTemplate, data: tpPoints });
    latDatasets.push({ ...datasetTemplate, data: latPoints });
    retxDatasets.push({ ...datasetTemplate, data: retxPoints });
  });

  chartGoodput.data.datasets = gpDatasets;
  chartThroughput.data.datasets = tpDatasets;
  chartLatency.data.datasets = latDatasets;
  chartRetx.data.datasets = retxDatasets;

  chartGoodput.update();
  chartThroughput.update();
  chartLatency.update();
  chartRetx.update();

  renderOptimalMatrix(matrixData);
}

function renderOptimalMatrix(matrixData) {
  const container = document.getElementById('optMatrixGrid');
  if (!container) return;
  container.innerHTML = '';

  matrixData.forEach((item) => {
    const div = document.createElement('div');
    div.className = 'opt-matrix-item';
    div.innerHTML = `
      <span class="opt-matrix-ber">BER = ${item.ber === 0 ? '0 (Clean)' : item.ber.toExponential(1)}</span>
      <span class="opt-matrix-size">${item.bestSize} Bytes</span>
      <span class="opt-matrix-gp">Peak: ${item.maxGp.toFixed(3)} Mbps</span>
    `;
    container.appendChild(div);
  });
}

// =============================================================================
// 7. WIRESHARK-STYLE PACKET INSPECTOR TABLE
// =============================================================================

function renderInspectorTable() {
  const tbody = document.getElementById('packetTableBody');
  const pageInfo = document.getElementById('pageInfo');
  const btnPrev = document.getElementById('btnPrevPage');
  const btnNext = document.getElementById('btnNextPage');

  let logs = state.liveLog;

  // Filter
  if (state.inspectorFilter === 'success') {
    logs = logs.filter(l => l.success);
  } else if (state.inspectorFilter === 'retry') {
    logs = logs.filter(l => l.attempts > 1);
  } else if (state.inspectorFilter === 'failed') {
    logs = logs.filter(l => !l.success);
  }

  // Search query
  if (state.inspectorQuery) {
    logs = logs.filter(l => 
      l.seq.toString().includes(state.inspectorQuery) ||
      (l.success ? 'success' : 'failed').includes(state.inspectorQuery)
    );
  }

  const total = logs.length;
  const start = (state.currentPage - 1) * state.pageSize;
  const end = Math.min(start + state.pageSize, total);
  const pageItems = logs.slice(start, end);

  tbody.innerHTML = '';

  if (total === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center empty-state">No packets matching filter. Run a simulation to populate.</td></tr>`;
    pageInfo.textContent = 'Showing 0 of 0 packets';
    btnPrev.disabled = true;
    btnNext.disabled = true;
    return;
  }

  pageItems.forEach((row) => {
    const tr = document.createElement('tr');
    const statusClass = !row.success ? 'fail' : row.attempts > 1 ? 'retx' : 'ok';
    const statusText = !row.success ? 'DROPPED' : row.attempts > 1 ? `RETX (${row.attempts})` : 'DELIVERED';

    tr.innerHTML = `
      <td><strong>#${row.seq}</strong></td>
      <td>${row.payload}</td>
      <td>${row.wire}</td>
      <td>${row.attempts}</td>
      <td><span class="status-badge ${statusClass}">${statusText}</span></td>
      <td>${row.start_s.toFixed(4)}s</td>
      <td>${row.end_s.toFixed(4)}s</td>
      <td>${(row.latency_s * 1000).toFixed(2)} ms</td>
    `;
    tbody.appendChild(tr);
  });

  pageInfo.textContent = `Showing ${start + 1}-${end} of ${total} packets`;
  btnPrev.disabled = state.currentPage <= 1;
  btnNext.disabled = end >= total;
}

// =============================================================================
// 8. CSV EXPORT
// =============================================================================

function exportLogsToCSV() {
  if (!state.liveLog || state.liveLog.length === 0) {
    // Generate one transfer simulation right now to export
    const cfg = computeLinkConfig();
    const sim = runTransferSimulation(cfg.totalBytes, state.payloadBytes, cfg);
    state.liveLog = sim.log;
  }

  let csv = "ber,size,seq,payload,attempts,success,start_s,end_s,latency_s\n";
  const cfg = computeLinkConfig();
  state.liveLog.forEach(r => {
    csv += `${cfg.ber},${state.payloadBytes},${r.seq},${r.payload},${r.attempts},${r.success},${r.start_s.toFixed(7)},${r.end_s.toFixed(7)},${r.latency_s.toFixed(7)}\n`;
  });

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.setAttribute('download', `per_packet_log_ber_${cfg.ber}_size_${state.payloadBytes}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  showNotification('CSV log file exported successfully! 📥');
}

// =============================================================================
// 9. PYTHON BACKEND INTEGRATION
// =============================================================================

async function checkBackendHealth() {
  try {
    const res = await fetch('/api/health', { cache: 'no-store' });
    if (res.ok) {
      state.isBackendOnline = true;
      const badge = document.getElementById('backendStatusBadge');
      badge.querySelector('.status-dot').className = 'status-dot online';
      badge.querySelector('.status-label').textContent = 'Backend Active';
    }
  } catch (e) {
    state.isBackendOnline = false;
    const badge = document.getElementById('backendStatusBadge');
    badge.querySelector('.status-dot').className = 'status-dot';
    badge.querySelector('.status-label').textContent = 'Client Engine';
  }
}

async function executePythonBackend() {
  const banner = document.getElementById('pythonExecBanner');
  const stdoutBox = document.getElementById('pythonStdout');
  const btn = document.getElementById('btnExecutePythonScript');

  banner.style.display = 'flex';
  btn.disabled = true;
  stdoutBox.textContent = 'Executing python packet_sim.py...\nPlease wait while Monte-Carlo trials finish.';

  try {
    const res = await fetch('/api/run-python', { method: 'POST' });
    const data = await res.json();
    banner.style.display = 'none';
    btn.disabled = false;

    if (data.success) {
      stdoutBox.textContent = data.stdout || 'Execution complete.';
      showNotification('packet_sim.py executed successfully! Refreshed graphs.');
      refreshGalleryImages();
    } else {
      stdoutBox.textContent = `Error:\n${data.stderr || data.detail || 'Execution failed'}`;
    }
  } catch (err) {
    banner.style.display = 'none';
    btn.disabled = false;
    stdoutBox.textContent = `Backend request error: ${err.message}\nMake sure python server.py is running!`;
  }
}

async function loadPythonSummaryCsv() {
  try {
    const res = await fetch('/api/results/summary');
    const json = await res.json();
    if (json.data && json.data.length > 0) {
      showNotification('Loaded official summary.csv data from Python! 📊');
      renderSummaryCsvToCharts(json.data);
    } else {
      showNotification('No summary.csv found yet. Click "Run packet_sim.py" in Python tab.');
    }
  } catch (e) {
    showNotification('Unable to fetch summary.csv from backend.');
  }
}

function renderSummaryCsvToCharts(records) {
  initCharts();
  const bers = [0.0, 1e-6, 1e-5, 5e-5, 1e-4];
  const gpDatasets = [];
  const tpDatasets = [];
  const latDatasets = [];
  const retxDatasets = [];
  const matrixData = [];

  bers.forEach((ber, bIdx) => {
    const color = CHART_COLORS[bIdx];
    const berRows = records.filter(r => Math.abs(r.ber - ber) < 1e-9);

    const gpPoints = [];
    const tpPoints = [];
    const latPoints = [];
    const retxPoints = [];
    let bestSize = 64;
    let maxGp = -1;

    PACKET_SIZES.forEach((size) => {
      const match = berRows.find(r => r.packet_size === size);
      if (match) {
        gpPoints.push(match.goodput_mbps_mean);
        tpPoints.push(match.throughput_mbps_mean);
        latPoints.push(match.avg_latency_ms_mean);
        retxPoints.push(match.retx_per_packet_mean);

        if (match.goodput_mbps_mean > maxGp) {
          maxGp = match.goodput_mbps_mean;
          bestSize = size;
        }
      } else {
        gpPoints.push(null);
        tpPoints.push(null);
        latPoints.push(null);
        retxPoints.push(null);
      }
    });

    matrixData.push({ ber, bestSize, maxGp });

    const template = {
      label: `BER=${ber === 0 ? '0' : ber.toExponential(0)}`,
      borderColor: color.border,
      backgroundColor: color.bg,
      borderWidth: 2,
      pointRadius: 4,
      tension: 0.3
    };

    gpDatasets.push({ ...template, data: gpPoints });
    tpDatasets.push({ ...template, data: tpPoints });
    latDatasets.push({ ...template, data: latPoints });
    retxDatasets.push({ ...template, data: retxPoints });
  });

  chartGoodput.data.datasets = gpDatasets;
  chartThroughput.data.datasets = tpDatasets;
  chartLatency.data.datasets = latDatasets;
  chartRetx.data.datasets = retxDatasets;

  chartGoodput.update();
  chartThroughput.update();
  chartLatency.update();
  chartRetx.update();

  renderOptimalMatrix(matrixData);
}

function refreshGalleryImages() {
  const imgs = document.querySelectorAll('.gallery-item img');
  const timestamp = Date.now();
  imgs.forEach(img => {
    const src = img.getAttribute('src').split('?')[0];
    img.src = `${src}?t=${timestamp}`;
  });
}

function showNotification(msg) {
  const existing = document.getElementById('toastNotice');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.id = 'toastNotice';
  toast.textContent = msg;
  document.body.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// =============================================================================
// 10. INITIALIZATION
// =============================================================================

window.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  updateSimulationCalculations();
  resetVisualizer();
  checkBackendHealth();

  // Run a quick silent simulation to populate the table initially
  const cfg = computeLinkConfig();
  const initSim = runTransferSimulation(cfg.totalBytes, state.payloadBytes, cfg);
  state.liveLog = initSim.log;
  renderInspectorTable();
});

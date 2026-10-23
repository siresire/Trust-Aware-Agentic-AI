/* model.js - how reliable Agent 1 is: its warning over time against the threshold, what changes if
   the threshold moves (sweep), whether a warning of 0.8 really means 80% (calibration), and the
   offline scores the training notebook printed. Measured, never typed in. */

let thrPick = null;

function renderProbChart() {
  const box = $('#probChart'); if (!box || !STATE.cfg) return;
  const ticks = (STATE.agent && STATE.agent.ticks) || [];
  const now = (STATE.live && STATE.live.now) || Date.now() / 1000;
  const last = ticks[ticks.length - 1];
  $('#probNow').textContent = last ? `now ${last.prob.toFixed(2)}, acts from ${STATE.cfg.warn_prob.toFixed(2)}` : '';
  timeChart(box, {
    label: 'Agent 1 warning', t0: now - 600, t1: now, height: 200, ymax: 1, spans: eventSpans((STATE.live || {}).events, now),
    series: [{ name: 'Warning', color: 'var(--agent)', data: ticks.map((t) => [t.t, t.prob]), fmt: (v) => v.toFixed(2) }],
    guides: [{ v: STATE.cfg.warn_prob, color: 'var(--ink)', label: 'threshold' }],
    yfmt: (v) => v.toFixed(1), empty: 'No agent snapshots yet. Start the agent or replay a run.',
  });
}

function renderModel() {
  renderProbChart();
  const m = STATE.model; if (!m) return;
  if (!m.snapshots) {
    $('#sweepNote').textContent = 'No recorded no-agent runs found in data/experiment2, so the sweep and calibration cannot be measured.';
    return;
  }
  if (thrPick === null) { thrPick = m.threshold; $('#thrRange').value = Math.round(m.threshold * 20); }
  const sw = m.sweep, cfgThr = m.threshold;
  const y2 = Math.ceil(Math.max(...sw.map((r) => r.calm_warnings_per_hour || 0)) / 100) * 100 || 100;
  xyChart($('#sweepChart'), {
    label: 'Threshold sweep', xmin: 0, xmax: 1, ymax: 100, y2max: y2, height: 260, xlabel: 'threshold (Agent 1 warns at or above this)',
    xfmt: (v) => v.toFixed(1), yfmt: (v) => Math.round(v) + '%', y2fmt: (v) => Math.round(v), tipx: (v) => 'threshold ' + v.toFixed(2),
    vline: { x: thrPick, label: thrPick === cfgThr ? `${thrPick.toFixed(2)}, the agent's setting` : thrPick.toFixed(2) },
    series: [
      { name: 'Jams warned in time', color: 'var(--ok)', data: sw.map((r) => [r.threshold, r.jams_caught_pct]), fmt: (v) => fx(v) + '%', dots: true },
      { name: 'Faults warned', color: 'var(--fault)', data: sw.map((r) => [r.threshold, r.faults_warned_pct]), fmt: (v) => fx(v) + '%', dots: true },
      { name: 'Calm false alarms per hour', color: 'var(--agent)', right: true, data: sw.map((r) => [r.threshold, r.calm_warnings_per_hour]), fmt: (v) => fx(v), dots: true },
    ],
  });
  const r = sw.reduce((a, b) => (Math.abs(b.threshold - thrPick) < Math.abs(a.threshold - thrPick) ? b : a));
  $('#thrVal').textContent = r.threshold.toFixed(2);
  $('#thrStats').innerHTML = [
    ['Jams warned in time', fx(r.jams_caught_pct) + '%'], ['Median warning time', fx(r.warning_delay_s, 1) + ' s into a jam'],
    ['Faults warned', fx(r.faults_warned_pct) + '%'], ['Calm false alarms', fx(r.calm_warnings_per_hour) + ' per hour'],
    ['Precision per snapshot', fx(r.precision * 100) + '%'], ['Recall per snapshot', fx(r.recall * 100) + '%'],
  ].map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('');
  $('#sweepNote').textContent = `Measured on runs ${m.runs.join(', ')} (no agent, so nothing interfered): ${m.jams} jams, ${m.faults} faults, ` +
    `${fx(m.calm_hours, 2)} calm hours, ${m.snapshots} snapshots. Agent 1 warns in almost every fault at any threshold: ` +
    'moving the threshold cannot tell a fault from a jam. That is the trust check\'s job.';

  const bins = m.bins.filter((b) => b.n);
  xyChart($('#calChart'), {
    label: 'Calibration', xmin: 0, xmax: 1, ymax: 1, height: 260, diagonal: true, xlabel: 'Agent 1 warning (mean in each band)',
    xfmt: (v) => v.toFixed(1), yfmt: (v) => v.toFixed(2), tipx: (v) => 'warning about ' + v.toFixed(2),
    series: [{ name: 'Really degraded within 6 s', color: 'var(--agent)', dots: true, data: bins.map((b) => [b.mean_prob, b.observed, b.n]),
      fmt: (v, p) => `${(v * 100).toFixed(0)}% of ${p[2]} snapshots` }],
  });
  $('#calStats').innerHTML = [['Brier score', fx(m.brier, 3)], ['Calibration error (ECE)', fx(m.ece, 3)],
    ['Snapshots that degraded', fx(m.base_rate * 100) + '%']].map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('');
  $('#calNote').textContent = 'Each dot is a band of warnings (dot size = how many snapshots). On the dashed line, a warning of 0.8 comes true 80% of the time. ' +
    '"Degraded" uses the same rule as the training labels (ml/label.py): 2 of the last 3 readings slow or lost, on any protected device, within 6 s. ' +
    'Lower Brier and ECE are better.';

  const o = m.offline;
  if (!o) { $('#offline').innerHTML = '<tbody><tr><td>The training notebook\'s scores were not found.</td></tr></tbody>'; return; }
  $('#offSrc').textContent = 'printed by ' + o.source;
  const cols = [['precision', 'Precision'], ['recall', 'Recall'], ['f1', 'F1'], ['onset_recall', 'Onset recall'], ['false_alarm_%', 'False alarms'], ['pr_auc', 'PR-AUC']];
  $('#offline').innerHTML = `<thead><tr><th>Model</th>${cols.map((c) => `<th>${c[1]}</th>`).join('')}</tr></thead><tbody>` +
    o.rows.map((r) => `<tr class="${r.model === 'trained model' ? 'hl' : ''}"><th>${esc(r.model === 'trained model' ? 'Agent 1 (trained model)' : 'Rule: ' + r.model)}</th>` +
      cols.map(([k]) => `<td>${num(r[k]) ? (k === 'false_alarm_%' ? fx(r[k], 2) + '%' : r[k].toFixed(3)) : '–'}</td>`).join('') + '</tr>').join('') + '</tbody>';
  $('#offNote').textContent = o.note + ' Onset recall: warned before the device was already bad.';
}

function setupModel() {
  $('#thrRange').addEventListener('input', (e) => { thrPick = +e.target.value / 20; renderModel(); });
}

/* compare.js - no agent vs prediction-only (ungated) vs trust-aware (gated), on the same recorded events.
   Table 1 numbers come from results/ (analysis/results.py, the paper's tables); the camera and rule
   numbers are measured here from the same runs' logs. */

const MODES3 = ['none', 'predict', 'trust'];
const MEASURES = [
  { group: 'Did it fix real jams?' },
  { k: 'jams_acted_pct', t: 'Jams acted on', d: 'Share of jams with at least one slow-down.', better: 'high', f: (v) => fx(v) + '%', max: 100 },
  { k: 'missed_jams', t: 'Missed corrections', d: 'Jams with no slow-down at all.', better: 'low', f: (v) => fx(v) },
  { k: 'first_slow_s', t: 'Time to first slow-down', d: 'Median seconds from the jam starting.', better: 'low', f: (v) => fx(v, 1) + ' s' },
  { k: 'hit_flooder_pct', t: 'Slow-downs that hit a flooder', d: 'During jams: was the slowed device one of the flooders?', better: 'high', f: (v) => fx(v) + '%', max: 100 },
  { group: 'Did it act when it should not?' },
  { k: 'unsafe_faults_pct', t: 'Unsafe actions in faults', d: 'Faults where a device was slowed. Slowing cannot fix a fault.', better: 'low', f: (v) => fx(v) + '%', max: 100 },
  { k: 'fault_slowed_s', t: 'Device-seconds slowed in faults', d: 'How long devices were wrongly held at 2 Mbit/s.', better: 'low', f: (v) => fx(v) + ' s' },
  { k: 'calm_per_hour', t: 'Unnecessary slow-downs', d: 'Slow-downs per hour of calm time (no event running).', better: 'low', f: (v) => fx(v, 1) + ' per h' },
  { k: 'calm_messages_per_hour', t: 'Homeowner messages in calm time', d: 'New messages per calm hour. A known weakness.', better: 'low', f: (v) => fx(v, 1) + ' per h' },
  { group: 'How did the camera do during jams?' },
  { k: 'camera_bad_jams_pct', t: 'Camera readings bad', d: 'Slower than normal or a ping lost, during jams.', better: 'low', f: (v) => fx(v) + '%', max: 100 },
  { k: 'camera_rtt_jams_ms', t: 'Camera delay', d: 'Median delay during jams. Normal is under ', better: 'low', f: (v) => fx(v) + ' ms', normal: true },
  { k: 'camera_loss_jams_pct', t: 'Camera ping loss', d: 'Mean loss during jams.', better: 'low', f: (v) => fx(v, 1) + '%' },
  { k: 'camera_recovery_s', t: 'Camera recovery', d: 'Median seconds from the jam starting until 3 good readings in a row.', better: 'low', f: (v) => fx(v, 1) + ' s' },
  { group: "Did it keep the homeowner's rules?" },
  { k: 'policy_violations', t: 'Rule violations', d: 'Protected device slowed, below 2 Mbit/s, or held past 60 s.', better: 'low', f: (v) => fx(v), zeroOk: true },
  { k: 'protected_bad_jams_pct', t: 'All protected readings bad in jams', d: 'All 7 protected devices, not just the camera.', better: 'low', f: (v) => fx(v) + '%', max: 100 },
];

function measureCard(m, M) {
  const vals = MODES3.map((k) => M[k][m.k]);
  const ok = vals.filter(num);
  const top = m.max || Math.max(1e-9, ...ok) * 1.08;
  const best = ok.length > 1 ? (m.better === 'low' ? Math.min(...ok) : Math.max(...ok)) : null;
  const desc = m.normal ? m.d + fx(STATE.cfg.normal_ms[STATE.cfg.watch]) + ' ms.' : m.d;
  return `<article class="measure">
    <h3>${esc(m.t)}</h3><p>${esc(desc)} <span class="dir">${m.better === 'low' ? 'Lower is better.' : 'Higher is better.'}</span></p>
    <ul class="bars3">${MODES3.map((k, i) => {
      const v = vals[i];
      return `<li class="m-${k}${num(v) && v === best ? ' best' : ''}"><span class="mn">${MODE_NAME[k]}</span>
        <span class="track"><span style="width:${num(v) ? Math.max(v > 0 ? 1.5 : 0, (v / top) * 100) : 0}%"></span></span>
        <span class="mv">${num(v) ? m.f(v) : '–'}</span></li>`;
    }).join('')}</ul></article>`;
}

function renderCompare() {
  const c = STATE.compare; if (!c) return;
  if (!c.found) {
    $('#cmpBanner').textContent = `No results found in ${c.results_dir}/. Run: .venv/bin/python -m analysis.results`;
    $('#measures').innerHTML = ''; return;
  }
  const M = c.modes, seeds = Object.keys(c.same_schedule);
  const allSame = seeds.every((s) => c.same_schedule[s]);
  $('#cmpBanner').textContent = (allSame ? `Same events for all three agents (seeds ${seeds.join(', ')}): ` : 'Check: the schedules differ. ') +
    `${M.trust.jams} jams and ${M.trust.faults} faults each.`;
  renderVerdict(M);
  renderTradeoff(M);
  renderKeyTable(M);
  let html = '';
  for (const m of MEASURES) {
    if (m.group) html += `${html ? '</div>' : ''}<h2 class="mgroup">${esc(m.group)}</h2><div class="mrow">`;
    else html += measureCard(m, M);
  }
  $('#measures').innerHTML = html + '</div>';

  const types = Object.keys(c.by_type);
  $('#byType').innerHTML = `<thead><tr><th>Event</th>${MODES3.map((k) => `<th>${MODE_NAME[k]}</th>`).join('')}</tr></thead><tbody>` +
    types.map((t) => `<tr><th>${t}<span class="sub">${t.startsWith('C_') ? 'jam: slowing helps' : 'fault: slowing cannot help'}</span></th>` +
      MODES3.map((k) => { const v = c.by_type[t][k]; return `<td><b>${fx(v.camera_bad_pct)}%</b> camera<span class="sub">${fx(v.protected_bad_pct)}% all protected</span></td>`; }).join('') +
      '</tr>').join('') + '</tbody>';
  $('#cmpSources').innerHTML = `
    <p>Jams, faults, slow-downs, calm time and messages: <code>${esc(c.results_dir)}/events_scored.csv</code> and <code>runs_scored.csv</code>, written by <code>analysis/results.py</code>. These are the paper's Table 1 numbers.</p>
    <p>Camera numbers: <code>data/raw/session_*/network_metrics/camera.log</code> during each event, judged against the camera's normal delay (${fx(STATE.cfg.normal_ms[STATE.cfg.watch])} ms, <code>config_ubuntu.yaml</code>).</p>
    <p>Rule violations: every SLOW and UNDO in <code>${esc(c.exp_dir)}/agent_*.jsonl</code>, checked against <code>models/homeowner_policy.json</code>.${MODES3.some((k) => M[k].policy_violations) ? ' Found: ' + esc(MODES3.flatMap((k) => M[k].violation_list).join('; ')) : ' None found.'}</p>`;

  const ev = c.events;
  $('#cmpEvents').innerHTML = `<thead><tr><th>Seed</th><th>Agent</th><th>Event</th><th>Devices</th><th>Length</th><th>Slow-downs</th><th>First</th><th>Hit flooder</th><th>Named as</th><th>Protected bad</th></tr></thead><tbody>` +
    ev.map((r) => `<tr><td>${fx(r.seed)}</td><td>${MODE_NAME[r.mode]}</td><td>${esc(r.type)}</td><td>${esc(String(r.devices).replace(/\|/g, ', '))}</td>
      <td>${fx(r.duration_s)} s</td><td>${fx(r.slowdowns)}</td><td>${r.first_slow_s === '' ? '–' : fx(r.first_slow_s, 1) + ' s'}</td>
      <td>${fx(r.slowed_flooder)}</td><td>${esc(r.named_as)}</td><td>${fx(r.protected_bad_pct)}%</td></tr>`).join('') + '</tbody>';
}

/* the answer, in one line */
function renderVerdict(M) {
  const n = M.none, p = M.predict, t = M.trust, k = 'camera_bad_jams_pct';
  const kept = (n[k] - t[k]) / (n[k] - p[k]), cut = 1 - t.calm_per_hour / p.calm_per_hour;
  $('#cmpHead').textContent = `Trust-aware: ${Math.round(kept * 100)}% of the protection, ${Math.round(cut * 100)}% fewer needless slow-downs`;
}

/* x: slow-downs when nothing needed fixing, y: camera readings fine during jams. Top left is best. */
function renderTradeoff(M) {
  const box = $('#tradeoff');
  const W = Math.max(300, box.clientWidth), H = 300, P = { l: 52, r: 24, t: 18, b: 46 };
  const iw = W - P.l - P.r, ih = H - P.t - P.b;
  const xmax = Math.ceil(Math.max(...MODES3.map((m) => M[m].calm_per_hour || 0)) / 25) * 25 || 25;
  const X = (v) => P.l + (v / xmax) * iw, Y = (v) => P.t + ih - (v / 100) * ih;
  box.innerHTML = '';
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, height: H, role: 'img', 'aria-label': 'Protection against wrong actions' }, box);
  el('rect', { class: 'best-zone', x: P.l, y: P.t, width: iw * 0.25, height: ih * 0.3 }, svg);
  el('text', { class: 'zone-label', x: P.l + 8, y: P.t + 16 }, svg).textContent = 'best: protects, rarely wrong';
  for (let i = 0; i <= 4; i++) {
    el('line', { class: 'grid', x1: P.l, x2: W - P.r, y1: Y(i * 25), y2: Y(i * 25) }, svg);
    el('text', { x: P.l - 8, y: Y(i * 25) + 4, 'text-anchor': 'end' }, svg).textContent = i * 25 + '%';
    el('text', { x: X((xmax * i) / 4), y: H - 24, 'text-anchor': 'middle' }, svg).textContent = Math.round((xmax * i) / 4);
  }
  el('text', { class: 'axis-label', x: P.l + iw / 2, y: H - 6, 'text-anchor': 'middle' }, svg).textContent =
    'slow-downs per hour when nothing was wrong (harm)';
  el('text', { class: 'axis-label', x: 12, y: P.t + ih / 2, transform: `rotate(-90 12 ${P.t + ih / 2})`, 'text-anchor': 'middle' }, svg).textContent =
    'camera fine during jams (benefit)';
  const pts = MODES3.map((m) => ({ m, x: M[m].calm_per_hour || 0, y: 100 - M[m].camera_bad_jams_pct }));
  el('path', { class: 'trade-link', d: `M${X(pts[0].x)} ${Y(pts[0].y)} L${X(pts[2].x)} ${Y(pts[2].y)} L${X(pts[1].x)} ${Y(pts[1].y)}` }, svg);
  for (const p of pts) {
    const g = el('g', { class: 'trade-pt m-' + p.m }, svg);
    el('circle', { cx: X(p.x), cy: Y(p.y), r: p.m === 'trust' ? 11 : 8 }, g);
    const right = X(p.x) < W - 170;
    el('text', { class: 'pt-name', x: X(p.x) + (right ? 16 : -16), y: Y(p.y) - 2, 'text-anchor': right ? 'start' : 'end' }, g).textContent = MODE_NAME[p.m];
    el('text', { class: 'pt-val', x: X(p.x) + (right ? 16 : -16), y: Y(p.y) + 14, 'text-anchor': right ? 'start' : 'end' }, g).textContent =
      `${fx(p.y)}% fine, ${fx(p.x, 1)} per h`;
  }
  $('#tradeNote').textContent = 'Up = camera fine during jams. Right = slow-downs when nothing was wrong.';
}

const KEY_ROWS = [
  { t: 'Camera fine during jams', why: 'protects what matters', v: (m) => 100 - m.camera_bad_jams_pct, f: (v) => fx(v) + '%', better: 'high' },
  { t: 'Jams acted on', why: 'does it react to real jams', v: (m) => m.jams_acted_pct, f: (v) => fx(v) + '%', better: 'high' },
  { t: 'Slowed the real flooder', why: 'picks the right device', v: (m) => m.hit_flooder_pct, f: (v) => fx(v) + '%', better: 'high' },
  { t: 'Faults with a wrong slow-down', why: 'acts where it cannot help', v: (m) => m.unsafe_faults_pct, f: (v) => fx(v) + '%', better: 'low' },
  { t: 'Slow-downs when nothing was wrong', why: 'per calm hour', v: (m) => m.calm_per_hour, f: (v) => fx(v, 1), better: 'low' },
  { t: 'Messages to the homeowner when calm', why: 'per calm hour, a weakness', v: (m) => m.calm_messages_per_hour, f: (v) => fx(v, 1), better: 'low' },
];

function renderKeyTable(M) {
  $('#keyTable').innerHTML = `<thead><tr><th></th>${MODES3.map((m) => `<th class="m-${m}">${MODE_NAME[m]}</th>`).join('')}</tr></thead><tbody>` +
    KEY_ROWS.map((r) => {
      const vals = MODES3.map((m) => r.v(M[m]));
      const ok = vals.filter((v, i) => num(v) && !(MODES3[i] === 'none' && r.better === 'high' && r.t !== 'Camera fine during jams'));
      const best = r.better === 'low' ? Math.min(...ok) : Math.max(...ok);
      return `<tr><th>${esc(r.t)}<span class="sub">${esc(r.why)}</span></th>` +
        vals.map((v) => `<td class="${num(v) && v === best ? 'best' : ''}">${num(v) ? r.f(v) : '–'}</td>`).join('') + '</tr>';
    }).join('') + '</tbody>';
}

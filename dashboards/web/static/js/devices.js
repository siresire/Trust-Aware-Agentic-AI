/* devices.js - the device table, and the page for one device. */

const STATE_TEXT = { healthy: 'Normal', warning: 'Slower than usual', critical: 'Struggling', stale: 'Not reporting', offline: 'Offline' };

function sparkSVG(points, normal) {
  const v = points.map((p) => p[1]).filter(num);
  if (v.length < 2) return '<svg class="spark"></svg>';
  const top = Math.max(...v, normal * 1.3), t0 = points[0][0], t1 = points[points.length - 1][0];
  const X = (t) => ((t - t0) / Math.max(1, t1 - t0)) * 140, Y = (r) => 28 - (r / top) * 26;
  let d = '', gap = true;
  for (const p of points) { if (!num(p[1])) { gap = true; continue; } d += (gap ? 'M' : 'L') + X(p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1); gap = false; }
  return `<svg class="spark" viewBox="0 0 140 30" preserveAspectRatio="none" aria-hidden="true"><line x1="0" x2="140" y1="${Y(normal)}" y2="${Y(normal)}"/><path d="${d}"/></svg>`;
}

function delayCell(d) {
  const r = d.metrics && d.metrics.rtt_ms, n = d.normal_ms || 150;
  if (!num(r)) return '<span class="delaynum">no reply</span>';
  const scale = n * 3, w = Math.min(100, (r / scale) * 100), cls = r >= n * 2 ? 'bad' : r > n ? 'over' : '';
  return `<span class="delaynum">${fx(r)} ms</span><span class="delaybar" title="normal ${fx(n)} ms"><span class="${cls}" style="width:${w}%"></span><i style="left:${(n / scale) * 100}%"></i></span>`;
}

function renderDevices() {
  const live = STATE.live, tb = $('#devtable'); if (!live) return;
  const a = agentNow(), slowed = a ? a.slowed : [];
  let html = '<thead><tr><th>Device</th><th>State</th><th>Delay now, against its normal</th><th>Loss</th><th class="hide-sm">Upload</th><th class="hide-sm">Last 2 minutes</th></tr></thead><tbody>';
  for (const name of STATE.cfg.devices) {
    const d = live.devices[name], m = d.metrics || {}, isSlow = slowed.includes(name);
    const st = isSlow ? 'slowed' : d.status;
    html += `<tr data-dev="${esc(name)}">
      <td><a class="dname" href="#/device/${esc(name)}">${esc(name)}</a><span class="kind">${esc(d.type)}, ${d.protected ? 'protected' : 'may be slowed'}</span></td>
      <td><span class="state ${st}">${isSlow ? 'Slowed by the agent' : STATE_TEXT[d.status] || d.status}</span></td>
      <td>${delayCell(d)}</td>
      <td>${num(m.loss_pct) ? fx(m.loss_pct) + '%' : '–'}</td>
      <td class="hide-sm">${kbps(m.tx_kbps)}</td>
      <td class="hide-sm">${sparkSVG(d.spark, d.normal_ms || 150)}</td></tr>`;
  }
  tb.innerHTML = html + '</tbody>';
  tb.querySelectorAll('tbody tr').forEach((tr) => tr.addEventListener('click', (e) => {
    if (e.target.tagName !== 'A') location.hash = '#/device/' + tr.dataset.dev;
  }));
}

/* one device */
const RANGES = [[5, '5 minutes'], [15, '15 minutes'], [60, '1 hour']];
let devRange = 5, devCache = null;

function setupRange() {
  const box = $('#devRange');
  box.innerHTML = RANGES.map(([m, t]) => `<button type="button" data-m="${m}" aria-pressed="${m === devRange}">${t}</button>`).join('');
  box.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => { devRange = +b.dataset.m; setupRange(); loadDevice(STATE.devName); }));
}

async function loadDevice(name) {
  if (!name) return;
  let d;
  try { d = await api(`/api/device/${encodeURIComponent(name)}`, `n=${devRange * 30 + 10}`); } catch (e) { return; }
  if (STATE.page !== 'device' || STATE.devName !== name) return;
  devCache = d; drawDevice();
}

function drawDevice() {
  const d = devCache; if (!d) return;
  const live = device(d.name), a = agentNow(), isSlow = a && a.slowed.includes(d.name);
  $('#devName').textContent = d.name;
  $('#devSub').textContent = `${d.type}, sends ${(d.protocol || 'unknown').toUpperCase()} traffic. ` +
    (d.protected ? 'Protected: the agent never slows it.' : 'The agent may slow it to 2 Mbit/s for up to 60 seconds during a jam.') +
    (isSlow ? ' It is slowed right now.' : '') + (d.protected ? '' : ' Shaded areas show when it was slowed.');
  const h = d.history, t1 = d.now, t0 = t1 - devRange * 60, n = d.normal_ms || 150;
  const last = h[h.length - 1] || {};
  $('#devRttNow').textContent = num(last.rtt_ms) ? `${fx(last.rtt_ms)} ms now, normal ${fx(n)} ms` : `normal ${fx(n)} ms`;
  $('#devTxNow').textContent = kbps(last.tx_kbps) + ' now';
  $('#devLossNow').textContent = num(last.loss_pct) ? fx(last.loss_pct) + '% now' : '';

  // shade the time the agent slowed this device (from its last 10 minutes)
  const spans = (STATE.agent && STATE.agent.ticks ? blocks(STATE.agent.ticks, (t) => ((t.slowed || []).includes(d.name) ? 's' : ''), 5) : [])
    .map((b) => ({ a: b.a, b: b.b, cls: 'slowspan' }));
  timeChart($('#devRtt'), { label: 'Delay', t0, t1, height: 260, spans,
    series: [{ name: 'Delay', color: 'var(--ok)', data: h.map((r) => [r.timestamp, r.rtt_ms]), fmt: (v) => fx(v) + ' ms' }],
    guides: [{ v: n, color: 'var(--ink-2)', label: 'normal' }, { v: n * 2, color: 'var(--jam)', label: 'twice normal' }],
    yfmt: (v) => Math.round(v) });
  timeChart($('#devTx'), { label: 'Upload', t0, t1, height: 170, spans,
    series: [{ name: 'Upload', color: 'var(--agent)', data: h.map((r) => [r.timestamp, r.tx_kbps]), fmt: kbps }],
    guides: d.protected ? [] : [{ v: 2000, color: 'var(--agent)', label: 'agent cap 2 Mbit/s' }],
    yfmt: (v) => (v >= 1000 ? (v / 1000).toFixed(1) + 'M' : Math.round(v) + 'k') });
  timeChart($('#devLoss'), { label: 'Ping loss', t0, t1, height: 170, ymax: 100, spans,
    series: [{ name: 'Loss', color: 'var(--jam)', data: h.map((r) => [r.timestamp, r.loss_pct]), fmt: (v) => fx(v) + '%' }],
    yfmt: (v) => Math.round(v) + '%' });
}

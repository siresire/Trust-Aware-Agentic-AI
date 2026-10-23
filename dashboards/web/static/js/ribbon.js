/* ribbon.js - the last 10 minutes in one picture: how full the line was, what Agent 1 wanted,
   what the trust check allowed, and which devices were slowed. */

const RIB = { span: 600 };

/* join snapshots in a row that share the same value into [start, end] blocks */
function blocks(ticks, test, gap) {
  const out = []; let cur = null;
  for (const t of ticks) {
    const v = test(t);
    if (v && cur && cur.v === v && t.t - cur.b <= gap) cur.b = t.t + 2;
    else if (v) { cur = { a: t.t, b: t.t + 2, v }; out.push(cur); }
    else cur = null;
  }
  return out;
}

function renderRibbon() {
  const box = $('#ribbon'); if (!box || !STATE.cfg) return;
  const ticks = (STATE.agent && STATE.agent.ticks) || [];
  const W = Math.max(320, box.clientWidth), narrow = W < 640;
  const L = narrow ? 70 : 168, R = 14;
  const rows = [
    { key: 'ev', label: narrow ? 'Event' : 'Event (events log)', h: 16 },
    { key: 'line', label: narrow ? 'Line' : 'Shared line', h: 80 },
    { key: 'prob', label: narrow ? 'Warning' : 'Agent 1 warning', h: 40 },
    { key: 'want', label: narrow ? 'Agent 1' : 'Agent 1 wanted to slow', h: 18 },
    { key: 'allow', label: narrow ? 'Allowed' : 'Trust check allowed', h: 18 },
    ...STATE.cfg.limitable.map((d) => ({ key: 'dev', dev: d, label: (narrow ? '' : 'Slowed: ') + d, h: 14 })),
  ];
  let y = 8; for (const r of rows) { r.y = y; y += r.h + (r.key === 'line' || r.key === 'prob' ? 14 : 8); }
  const H = y + 22;
  box.innerHTML = '';
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, height: H, role: 'img', 'aria-label': 'The last 10 minutes of the network and the agent' }, box);

  const now = (STATE.live && STATE.live.now) || Date.now() / 1000, t1 = now, t0 = now - RIB.span;
  const X = (t) => L + ((Math.max(t0, Math.min(t1, t)) - t0) / RIB.span) * (W - L - R);
  for (const r of rows) {
    el('text', { class: 'track-label', x: 0, y: r.y + r.h / 2 + 4 }, svg).textContent = r.label;
    if (r.key !== 'line' && r.key !== 'prob') el('rect', { class: 'lane', x: L, y: r.y, width: W - L - R, height: r.h, rx: 3 }, svg);
  }
  const line = rows[1], Yl = (u) => line.y + line.h - Math.min(1, u) * line.h;

  // problem bands behind everything
  for (const b of blocks(ticks, (t) => (t.steady === 'jam' ? 'jam' : t.steady && t.steady.includes('fault') ? 'fault' : ''), 5)) {
    el('rect', { class: b.v, x: X(b.a), y: line.y, width: Math.max(2, X(b.b) - X(b.a)), height: y - line.y - 8 }, svg);
  }
  // what really happened (the events log is the answer sheet)
  for (const e of (STATE.live && STATE.live.events) || []) {
    const x = X(e.start), w = Math.max(3, X(e.end || now) - x);
    el('rect', { class: 'ev-bar ' + (e.type.startsWith('C_') ? 'ev-jam' : 'ev-fault'), x, y: rows[0].y, width: w, height: rows[0].h, rx: 3 }, svg);
    const short = { C_SEVERE: 'jam', C_BORDER: 'small jam', F_WAN: 'WAN' }[e.type] || (e.devices[0] || 'device');
    const name = w > 90 ? `${e.type} ${e.type === 'F_DEVLINK' ? e.devices.join(', ') : ''}` : short;
    if (w > 22) el('text', { class: 'ev-text', x: x + 4, y: rows[0].y + 12 }, svg).textContent = name.length * 6 > w ? name.slice(0, Math.max(1, Math.floor(w / 6.5))) : name;
  }
  for (const v of [0, 0.5, 1]) {
    el('line', { class: 'grid', x1: L, x2: W - R, y1: Yl(v), y2: Yl(v) }, svg);
    el('text', { x: L - 8, y: Yl(v) + 4, 'text-anchor': 'end' }, svg).textContent = Math.round(v * 100) + '%';
  }
  el('line', { class: 'limit', x1: L, x2: W - R, y1: Yl(STATE.cfg.link_full), y2: Yl(STATE.cfg.link_full) }, svg);

  // line usage: from the router's own log if there is one, else from the agent's snapshots
  let pts = ((STATE.live && STATE.live.uplink.history) || []).filter((p) => p[0] >= t0);
  if (pts.length < 2) pts = ticks.filter((t) => t.t >= t0).map((t) => [t.t, t.link]);
  if (pts.length > 1) {
    let d = '';
    pts.forEach((p, i) => (d += (i && p[0] - pts[i - 1][0] <= 8 ? 'L' : 'M') + X(p[0]).toFixed(1) + ' ' + Yl(p[1]).toFixed(1)));
    el('path', { class: 'area', d: `M${X(pts[0][0])} ${Yl(0)}` + d.replace(/^M/, 'L') + `L${X(pts[pts.length - 1][0])} ${Yl(0)}Z` }, svg);
    el('path', { class: 'line', d }, svg);
  }

  // Agent 1's warning against its threshold
  const pr = rows[2], Yp = (v) => pr.y + pr.h - Math.min(1, v) * pr.h;
  el('line', { class: 'grid', x1: L, x2: W - R, y1: Yp(0), y2: Yp(0) }, svg);
  el('line', { class: 'thr', x1: L, x2: W - R, y1: Yp(STATE.cfg.warn_prob), y2: Yp(STATE.cfg.warn_prob) }, svg);
  el('text', { x: L - 8, y: Yp(STATE.cfg.warn_prob) + 4, 'text-anchor': 'end' }, svg).textContent = STATE.cfg.warn_prob.toFixed(1);
  const pp = ticks.filter((t) => t.t >= t0);
  if (pp.length > 1) {
    let d = '';
    pp.forEach((p, i) => (d += (i && p.t - pp[i - 1].t <= 8 ? 'L' : 'M') + X(p.t).toFixed(1) + ' ' + Yp(p.prob).toFixed(1)));
    el('path', { class: 'prob-line', d }, svg);
  }

  // the decisions
  const lane = (r, test, cls) => {
    for (const b of blocks(ticks, test, 5)) {
      const x = X(b.a), w = Math.max(3, X(b.b) - x);
      el('rect', { class: cls, x: cls === 'want' ? x + 0.75 : x, y: r.y + (cls === 'want' ? 0.75 : 0), width: cls === 'want' ? Math.max(2, w - 1.5) : w, height: r.h - (cls === 'want' ? 1.5 : 0), rx: 3 }, svg);
    }
  };
  lane(rows[3], (t) => (t.a1 && t.a1.startsWith('slow') ? 'w' : ''), 'want');
  lane(rows[4], (t) => (t.a2 === 'APPROVE' || (t.a1 && t.a1.startsWith('slow') && STATE.agent.mode === 'predict') ? 'a' : ''), 'allow');
  for (const r of rows.slice(5)) lane(r, (t) => ((t.slowed || []).includes(r.dev) ? 's' : ''), 'slow-bar');

  // time axis
  for (let m = 10; m >= 0; m -= narrow ? 5 : 2) {
    const t = t1 - m * 60;
    el('text', { x: X(t), y: H - 4, 'text-anchor': m === 10 ? 'start' : m === 0 ? 'end' : 'middle' }, svg).textContent = m ? `${m} min ago` : 'now';
  }
  if (!ticks.length) {
    el('text', { class: 'empty', x: L + (W - L - R) / 2, y: rows[4].y + 14, 'text-anchor': 'middle' }, svg).textContent =
      'No agent decisions yet. Start the agent and they appear here.';
  }

  // hover: read one moment
  const cursor = el('line', { class: 'cursor', x1: -9, x2: -9, y1: 4, y2: y - 6 }, svg);
  svg.addEventListener('mousemove', (e) => {
    const r = svg.getBoundingClientRect(), px = ((e.clientX - r.left) / r.width) * W;
    if (px < L || px > W - R || !ticks.length) { hideTip(); cursor.setAttribute('x1', -9); cursor.setAttribute('x2', -9); return; }
    const t = t0 + ((px - L) / (W - L - R)) * RIB.span;
    let best = ticks[0]; for (const k of ticks) if (Math.abs(k.t - t) < Math.abs(best.t - t)) best = k;
    if (Math.abs(best.t - t) > 6) { hideTip(); return; }
    cursor.setAttribute('x1', X(best.t)); cursor.setAttribute('x2', X(best.t));
    const ev = ((STATE.live && STATE.live.events) || []).find((e) => best.t >= e.start && best.t <= (e.end || now));
    showTip(`<b>${clock(best.t)}</b>` + tipRow('Event', ev ? ev.type : 'none') + tipRow('Agent 1 warning', best.prob.toFixed(2)) + tipRow('Shared line', pct(best.link)) + tipRow('Agent 2 named it', best.steady === 'ok' ? 'no problem' : best.steady) +
      tipRow('Agent 1', best.a1.startsWith('slow') ? `slow the ${best.a1.slice(5)}` : 'nothing') +
      tipRow('Trust check', { APPROVE: 'allowed', REFUSE: 'refused', OK: 'nothing to check' }[best.a2] || best.a2) +
      tipRow('Slowed', best.slowed && best.slowed.length ? list(best.slowed) : 'none'), e.clientX, e.clientY);
  });
  svg.addEventListener('mouseleave', () => { hideTip(); cursor.setAttribute('x1', -9); cursor.setAttribute('x2', -9); });
}

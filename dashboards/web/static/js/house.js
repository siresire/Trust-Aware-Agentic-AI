/* house.js - the map of the house: devices -> home switch -> shared line (with the agent guarding it) -> router -> internet. */

const HOUSE = { built: false, chips: {}, wires: {} };
const CHIP = { x: 16, w: 262, h: 34, step: 40 };

function chipY(name) {
  const p = STATE.cfg.protected.indexOf(name);
  if (p >= 0) return 44 + p * CHIP.step;
  return 362 + STATE.cfg.limitable.indexOf(name) * CHIP.step;
}

function buildHouse() {
  const svg = $('#house'); svg.innerHTML = '';
  svg.setAttribute('viewBox', '0 0 920 490');
  const wires = el('g', {}, svg), nodes = el('g', {}, svg);
  el('text', { class: 'group-label', x: CHIP.x, y: 30 }, nodes).textContent = 'Protected: never slowed (delay and loss shown)';
  el('text', { class: 'group-label', x: CHIP.x, y: 348 }, nodes).textContent = 'May be slowed by the agent (upload shown)';

  const SW = { x: 312, y: 228, w: 104, h: 56 };
  for (const name of [...STATE.cfg.protected, ...STATE.cfg.limitable]) {
    const y = chipY(name), cy = y + CHIP.h / 2, sx = CHIP.x + CHIP.w;
    HOUSE.wires[name] = el('path', { class: 'wire flow', d: `M${sx} ${cy} C ${sx + 40} ${cy}, ${SW.x - 40} ${SW.y + SW.h / 2}, ${SW.x} ${SW.y + SW.h / 2}` }, wires);
    const g = el('g', { class: 'dev', tabindex: 0, role: 'link', 'aria-label': name }, nodes);
    if (name === STATE.cfg.watch) el('rect', { class: 'watch-ring', x: CHIP.x - 4, y: y - 4, width: CHIP.w + 8, height: CHIP.h + 8, rx: 10 }, g);
    el('rect', { x: CHIP.x, y, width: CHIP.w, height: CHIP.h, rx: 7 }, g);
    el('circle', { class: 'dot', cx: CHIP.x + 15, cy, r: 4.5 }, g);
    el('text', { class: 'name', x: CHIP.x + 28, y: cy + 5 }, g).textContent = name;
    const val = el('text', { class: 'val', x: CHIP.x + CHIP.w - 12, y: cy + 4.5, 'text-anchor': 'end' }, g);
    g.addEventListener('click', () => (location.hash = '#/device/' + name));
    g.addEventListener('keydown', (e) => { if (e.key === 'Enter') location.hash = '#/device/' + name; });
    g.addEventListener('mousemove', (e) => showTip(deviceTip(name), e.clientX, e.clientY));
    g.addEventListener('mouseleave', hideTip);
    HOUSE.chips[name] = { g, val };
  }

  const box = (x, y, w, h, title, sub) => {
    const g = el('g', { class: 'node' }, nodes);
    el('rect', { x, y, width: w, height: h, rx: 10 }, g);
    el('text', { class: 'name', x: x + w / 2, y: y + h / 2 - 2, 'text-anchor': 'middle' }, g).textContent = title;
    el('text', { class: 'sub', x: x + w / 2, y: y + h / 2 + 15, 'text-anchor': 'middle' }, g).textContent = sub;
  };
  box(SW.x, SW.y, SW.w, SW.h, 'Home switch', 's1');
  box(726, SW.y, 92, SW.h, 'Router', '10 Mbit/s out');
  box(836, SW.y, 74, SW.h, 'Internet', 'cloud');
  el('line', { class: 'wire', x1: 416, y1: 256, x2: 446, y2: 256 }, wires);
  el('line', { class: 'wire', x1: 706, y1: 256, x2: 726, y2: 256 }, wires);
  el('line', { class: 'wire', x1: 818, y1: 256, x2: 836, y2: 256 }, wires);

  // the shared line, drawn as a gauge that fills up
  el('text', { class: 'pipe-label', x: 446, y: 232 }, nodes).textContent = 'Shared line to the router';
  el('rect', { class: 'pipe-bg', x: 446, y: 241, width: 260, height: 30, rx: 6 }, nodes);
  HOUSE.fill = el('rect', { class: 'pipe-fill', x: 447, y: 242, width: 0, height: 28, rx: 5 }, nodes);
  el('line', { class: 'pipe-mark', x1: 446 + 260 * 0.8, x2: 446 + 260 * 0.8, y1: 236, y2: 276 }, nodes);
  el('text', { class: 'pipe-label', x: 446 + 260 * 0.8, y: 292, 'text-anchor': 'middle' }, nodes).textContent = 'full';
  HOUSE.pct = el('text', { class: 'pipe-value', x: 446, y: 318 }, nodes);
  HOUSE.rate = el('text', { class: 'pipe-label', x: 520, y: 316 }, nodes);

  // the agent, guarding the shared line
  el('line', { class: 'wire', x1: 576, y1: 194, x2: 576, y2: 241, 'stroke-dasharray': '3 4' }, wires);
  HOUSE.gate = el('g', { class: 'gate' }, nodes);
  el('rect', { x: 446, y: 96, width: 260, height: 98, rx: 10 }, HOUSE.gate);
  el('text', { class: 'name', x: 462, y: 122 }, HOUSE.gate).textContent = 'The agent';
  HOUSE.g1 = el('text', { class: 'sub', x: 462, y: 148 }, HOUSE.gate);
  HOUSE.g2 = el('text', { class: 'sub', x: 462, y: 170 }, HOUSE.gate);
  HOUSE.built = true;
}

function deviceTip(name) {
  const d = device(name); if (!d) return esc(name);
  const m = d.metrics || {}, a = agentNow(), slowed = a && a.slowed.includes(name);
  return `<b>${esc(name)}</b>` + tipRow('Delay now', num(m.rtt_ms) ? fx(m.rtt_ms) + ' ms' : 'no reply') + tipRow('Normal delay', fx(d.normal_ms) + ' ms') +
    tipRow('Ping loss', fx(m.loss_pct) + '%') + tipRow('Upload', kbps(m.tx_kbps)) + tipRow('Protocol', (d.protocol || '–').toUpperCase()) +
    (slowed ? tipRow('Agent', 'slowed to 2 Mbit/s') : '') + (d.issues.length ? `<div class="row"><span>${esc(d.issues.map((i) => i.text).join(', '))}</span></div>` : '');
}

function renderHouse() {
  const live = STATE.live; if (!live || !STATE.cfg) return;
  if (!HOUSE.built) buildHouse();
  const a = agentNow(), slowed = a ? a.slowed : [];
  for (const name in HOUSE.chips) {
    const d = live.devices[name], m = d.metrics || {}, c = HOUSE.chips[name], isSlow = slowed.includes(name);
    const tx = m.tx_kbps || 0, flood = !d.protected && tx >= STATE.cfg.link_kbps * 0.25;
    c.g.setAttribute('class', 'dev ' + d.status + (isSlow ? ' slowed' : '') + (flood ? ' flood' : '') + (name === STATE.cfg.watch ? ' watched' : ''));
    const rtt = num(m.rtt_ms) ? `${fx(m.rtt_ms)} ms` : 'no reply', lost = m.loss_pct ? `, ${fx(m.loss_pct)}% lost` : '';
    c.val.textContent = d.status === 'stale' || d.status === 'offline' ? d.status
      : isSlow ? `slowed, ${kbps(tx)} up`
      : d.protected ? rtt + lost : `${kbps(tx)} up${lost}`;
    const w = HOUSE.wires[name];
    w.setAttribute('class', 'wire ' + (isSlow ? 'slowed' : flood ? 'flood flow' : d.status === 'critical' ? 'critical flow' : 'flow'));
    w.style.strokeWidth = (1.6 + Math.min(5, tx / 1500)).toFixed(1);
    w.style.animationDuration = Math.max(0.35, Math.min(6, 1800 / (tx + 60))) + 's';
  }
  const u = live.uplink.util, full = STATE.cfg.link_full;
  HOUSE.fill.setAttribute('width', Math.max(0, Math.min(1, u)) * 258);
  HOUSE.fill.setAttribute('class', 'pipe-fill' + (u >= full ? ' full' : u >= 0.6 ? ' busy' : ''));
  HOUSE.pct.textContent = pct(u);
  HOUSE.rate.textContent = `${kbps(live.uplink.kbps)} of 10 Mbit/s leaving the house`;

  let cls = 'gate', l1 = 'Not running', l2 = 'Start agent/run_agent.py to see it here.';
  if (a) {
    if (a.slowed.length) { cls += ' acting'; l1 = `Slowing ${list(a.slowed)}`; l2 = a.steady === 'jam' ? 'because the line is full (a jam)' : 'until its 60-second limit ends'; }
    else if (a.a2 === 'REFUSE') { cls += ' refusing'; l1 = `Refused to slow the ${a.a1.slice(5)}`; l2 = a.steady === 'ok' ? 'waiting until the problem is clear' : `the line is not full: ${a.steady}`; }
    else if (a.a2 === 'APPROVE') { cls += ' acting'; l1 = 'Allowed a slow-down'; l2 = 'the line is full (a jam)'; }
    else { l1 = 'Watching, nothing to do'; l2 = `checks every 2 seconds (${a.mode} mode)`; }
  }
  HOUSE.gate.setAttribute('class', cls); HOUSE.g1.textContent = l1; HOUSE.g2.textContent = l2;
  const floods = STATE.cfg.limitable.filter((n) => (live.devices[n].metrics.tx_kbps || 0) >= STATE.cfg.link_kbps * 0.25);
  $('#houseAside').textContent = `${live.summary.online} of 10 devices reporting` + (floods.length ? `. Sending the most: ${list(floods)}` : '');
}

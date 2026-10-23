/* util.js - shared state and small helpers. Loaded first. */

const STATE = { cfg: null, live: null, agent: null, page: 'overview',
  src: { kind: 'live', session: null, at: null } };   // where the numbers come from (source.js)

/* the query string that tells the server which source to read */
function srcQuery(extra = '') {
  const s = STATE.src;
  const q = s.kind === 'replay' && s.session ? `src=replay&session=${s.session}` + (s.at ? `&at=${s.at.toFixed(2)}` : '') : '';
  return [q, extra].filter(Boolean).join('&');
}
const api = (path, extra) => getJSON(path + (srcQuery(extra) ? '?' + srcQuery(extra) : ''));
const MODE_NAME = { none: 'No agent', predict: 'Prediction-only', trust: 'Trust-aware' };
const mmss = (s) => (num(s) ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}` : '–');

const $ = (s) => document.querySelector(s);
const SVGNS = 'http://www.w3.org/2000/svg';
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const num = (v) => v != null && isFinite(v);
const fx = (v, d = 0) => (num(v) ? Number(v).toFixed(d) : '–');
const pct = (v) => (num(v) ? Math.round(v * 100) + '%' : '–');
const kbps = (v) => (!num(v) ? '–' : v >= 1000 ? (v / 1000).toFixed(1) + ' Mbit/s' : Math.round(v) + ' kbit/s');
const clock = (t) => new Date(t * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
const list = (a) => (a.length < 2 ? a.join('') : a.slice(0, -1).join(', ') + ' and ' + a[a.length - 1]);

async function getJSON(path) {
  const r = await fetch(path, { cache: 'no-store' });
  if (!r.ok) throw new Error(path + ' ' + r.status);
  return r.json();
}

/* make an SVG element: el('rect', {x: 1}, parent) */
function el(tag, attrs = {}, parent = null) {
  const e = document.createElementNS(SVGNS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}

/* one tooltip for the whole page */
function showTip(html, x, y) {
  const t = $('#tip');
  t.innerHTML = html; t.hidden = false;
  const w = t.offsetWidth, h = t.offsetHeight;
  t.style.left = Math.min(x + 16, innerWidth - w - 12) + 'px';
  t.style.top = Math.min(y + 14, innerHeight - h - 12) + 'px';
}
function hideTip() { $('#tip').hidden = true; }
const tipRow = (k, v) => `<div class="row"><span>${esc(k)}</span><span>${esc(v)}</span></div>`;

async function postJSON(path, body) {
  const r = await fetch(path, { method: 'POST', cache: 'no-store', headers: { 'X-Dashboard': '1', 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body) });
  return r.json();
}

/* the agent counts as running if its newest snapshot is under 10 s old */
const agentNow = () => (STATE.live && STATE.live.agent && STATE.live.agent.age < 10 ? STATE.live.agent : null);
const normalOf = (dev) => (STATE.cfg && STATE.cfg.normal_ms[dev]) || 150;
const device = (name) => STATE.live && STATE.live.devices[name];

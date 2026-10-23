/* app.js - page switching and fetching. Loaded last. */

const PAGES = ['overview', 'decisions', 'compare', 'model', 'devices', 'device', 'rules'];

function route() {
  const [page, arg] = location.hash.replace(/^#\/?/, '').split('/');
  STATE.page = page === 'device' && arg ? 'device' : PAGES.includes(page) ? page : 'overview';
  STATE.devName = STATE.page === 'device' ? decodeURIComponent(arg) : null;
  document.querySelectorAll('.page').forEach((p) => p.classList.toggle('on', p.id === 'page-' + STATE.page));
  document.querySelectorAll('nav a').forEach((a) => {
    const on = a.dataset.page === STATE.page || (STATE.page === 'device' && a.dataset.page === 'devices');
    a.classList.toggle('on', on);
    if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  hideTip();
  if (STATE.page === 'device') { devCache = null; setupRange(); loadDevice(STATE.devName); }
  if (STATE.page === 'rules') loadRules();
  scrollTo(0, 0);
  refreshAll();
}

function render() {
  try {
    renderSourceBar();
    if (STATE.page === 'overview') { renderStory(); renderTrust(); renderHouse(); renderCamera(); renderRibbon(); }
    else if (STATE.page === 'decisions') renderDecisions();
    else if (STATE.page === 'compare') renderCompare();
    else if (STATE.page === 'model') renderModel();
    else if (STATE.page === 'devices') renderDevices();
    else if (STATE.page === 'device') drawDevice();
    else if (STATE.page === 'rules') renderRulesStatus();
  } catch (e) { console.error(e); }
}

function setPulse(ok) {
  const p = $('#pulse'), live = STATE.live;
  const replay = STATE.src.kind === 'replay';
  p.className = 'pulse ' + (!ok ? 'stale' : replay ? 'replay' : live && live.summary.online ? 'live' : '');
  $('#pulseText').textContent = !ok ? 'Dashboard server not reachable'
    : replay ? (REPLAY.playing ? `Replaying at ${REPLAY.speed}×` : 'Replay paused')
    : !live || !live.summary.online ? 'Network not running'
    : agentNow() ? 'Live, agent running' : 'Live, agent not running';
}

/* fetch what the current page needs; answers for an older source or position are dropped */
let gen = 0, busy = false;
async function refreshAll(full = true) {
  const my = ++gen, p = STATE.page;
  const want = [api('/api/live').then((d) => ['live', d])];
  if (full || p === 'overview' || p === 'model' || p === 'decisions') want.push(api('/api/agent').then((d) => ['agent', d]));
  if (p === 'overview') want.push(api('/api/camera').then((d) => ['camera', d]));
  if (p === 'decisions') want.push(api('/api/decisions').then((d) => ['decisions', d]));
  if (p === 'compare' && !STATE.compare) want.push(getJSON('/api/compare').then((d) => ['compare', d]));
  if (p === 'model' && !STATE.model) want.push(getJSON('/api/model').then((d) => ['model', d]));
  try {
    const got = await Promise.all(want);
    if (my !== gen) return;                      // a newer request has started: this one is stale
    for (const [k, d] of got) STATE[k] = d;
    setPulse(true);
    render();
  } catch (e) {
    if (my === gen) setPulse(false);
  }
}

async function start() {
  for (;;) {
    try { STATE.cfg = await getJSON('/api/config'); break; }
    catch (e) { setPulse(false); await new Promise((r) => setTimeout(r, 2000)); }
  }
  setupSource(); setupDecisions(); setupModel(); setupRules();
  await loadSessions();
  addEventListener('hashchange', route);
  route();
  let last = performance.now(), n = 0;
  setInterval(async () => {
    const t = performance.now(), dt = (t - last) / 1000; last = t;
    tickReplay(dt);
    if (busy) return;
    busy = true;
    n += 1;
    const replayMoving = STATE.src.kind === 'replay' && REPLAY.playing;
    const slowPage = ['decisions', 'compare', 'model', 'rules'].includes(STATE.page);
    if (STATE.src.kind === 'live' || replayMoving) {
      if (!slowPage || n % 3 === 0) await refreshAll(false);
    }
    if (STATE.page === 'device' && n % 4 === 0) loadDevice(STATE.devName);
    busy = false;
  }, 1000);
  let rt; addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(render, 150); });
}
start();

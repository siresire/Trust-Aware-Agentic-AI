/* source.js - the bar under the header: Live (with agent start/stop) or Replay (pick a recorded run,
   play it, scrub through it). Every other part of the page just reads STATE and never cares which. */

const REPLAY = { playing: false, speed: 10, sessions: [], last: 0 };
let agentMode = 'trust';

function say(msg, tone = '') {
  const p = $('#ctlMsg');
  p.textContent = msg; p.hidden = !msg; p.className = 'ctl-msg ' + tone;
  clearTimeout(say.t); if (msg) say.t = setTimeout(() => (p.hidden = true), 9000);
}

function setSource(kind) {
  document.querySelectorAll('#sourcebar > .seg button').forEach((b) => b.setAttribute('aria-pressed', b.dataset.src === kind));
  $('#liveCtl').hidden = kind !== 'live';
  $('#replayCtl').hidden = kind !== 'replay';
  if (kind === 'live') {
    STATE.src = { kind: 'live', session: null, at: null };
    REPLAY.playing = false;
  } else {
    const sid = +$('#sessionPick').value || (REPLAY.sessions[0] && REPLAY.sessions[0].session);
    if (!sid) { say('No recorded runs found in data/experiment2 and data/raw.', 'bad'); setSource('live'); return; }
    STATE.src = { kind: 'replay', session: sid, at: null };
  }
  resetViews();
  refreshAll();
}

function resetViews() {
  STATE.live = null; STATE.agent = null; STATE.camera = null; STATE.decisions = null;
  if (typeof HOUSE !== 'undefined') HOUSE.built = false;
}

async function loadSessions() {
  try { REPLAY.sessions = await getJSON('/api/sessions'); } catch (e) { REPLAY.sessions = []; }
  const bySeed = {};
  for (const s of REPLAY.sessions) (bySeed[s.seed] = bySeed[s.seed] || []).push(s);
  $('#sessionPick').innerHTML = Object.keys(bySeed).map((seed) => `<optgroup label="Seed ${esc(seed)}: same events in each run">` +
    bySeed[seed].map((s) => `<option value="${s.session}"${s.mode === 'trust' && seed == Object.keys(bySeed)[0] ? ' selected' : ''}>` +
      `${MODE_NAME[s.mode] || s.mode}, run ${s.session}</option>`).join('') + '</optgroup>').join('') ||
    '<option value="">No recorded runs found</option>';
  document.querySelector('[data-src="replay"]').disabled = !REPLAY.sessions.length;
}

function renderSourceBar() {
  const live = STATE.live; if (!live) return;
  const src = live.source;
  if (src.kind === 'replay') {
    if (STATE.src.at === null) STATE.src.at = src.at;
    const len = src.length || 1, pos = src.at - src.t0;
    $('#scrubRange').value = Math.round((pos / len) * 1000);
    $('#replayPos').textContent = `${mmss(pos)} of ${mmss(len)}` + (live.event_now ? `, ${live.event_now.type} running` : '');
    $('#playBtn').textContent = REPLAY.playing ? 'Pause' : 'Play';
    $('#playBtn').setAttribute('aria-label', REPLAY.playing ? 'Pause' : 'Play');
    const svg = $('#scrubMarks');
    if (svg.dataset.session !== String(src.session)) {
      svg.dataset.session = src.session; svg.innerHTML = '';
      svg.setAttribute('viewBox', '0 0 1000 10'); svg.setAttribute('preserveAspectRatio', 'none');
      for (const e of src.events) {
        el('rect', { x: ((e.start - src.t0) / len) * 1000, y: 0, width: Math.max(3, (((e.end || src.t1) - e.start) / len) * 1000), height: 10,
          class: e.type.startsWith('C_') ? 'sm-jam' : 'sm-fault' }, svg);
      }
    }
    return;
  }
  // live: how fresh is the data, and is the agent running?
  const a = live.agent, ctl = live.control || {};
  const fresh = live.data_age == null ? 'No network data yet'
    : live.data_age > STATE.cfg.stale_after ? `Network data is ${Math.round(live.data_age)} s old: is Mininet still running?`
    : `Data ${fx(live.data_age, 1)} s old`;
  const ag = a ? (a.age < 10 ? `, agent ${fx(a.age, 1)} s` : `, agent last seen ${Math.round(a.age)} s ago`) : '';
  $('#fresh').textContent = fresh + ag;
  $('#fresh').className = 'fresh' + (live.data_age > STATE.cfg.stale_after || live.data_age == null ? ' stale' : '');
  const running = ctl.running || !!agentNow();
  $('#agentStart').disabled = running;
  $('#agentStop').disabled = !running;
  $('#agentStart').title = ctl.can_control ? '' : 'Start the dashboard with sudo to control the agent from here';
  $('#agentStop').title = $('#agentStart').title;
  document.querySelectorAll('#modePick button').forEach((b) => {
    const cur = running && agentNow() ? agentNow().mode : agentMode;
    b.setAttribute('aria-pressed', b.dataset.mode === cur);
    b.disabled = running;
  });
}

function tickReplay(dt) {
  if (STATE.src.kind !== 'replay' || !REPLAY.playing || STATE.src.at === null || !STATE.live) return;
  const src = STATE.live.source;
  STATE.src.at = Math.min(src.t1, STATE.src.at + dt * REPLAY.speed);
  if (STATE.src.at >= src.t1) REPLAY.playing = false;
}

function setupSource() {
  document.querySelectorAll('#sourcebar > .seg button').forEach((b) => b.addEventListener('click', () => setSource(b.dataset.src)));
  $('#sessionPick').addEventListener('change', () => { STATE.src = { kind: 'replay', session: +$('#sessionPick').value, at: null }; resetViews(); refreshAll(); });
  $('#speedPick').addEventListener('change', (e) => (REPLAY.speed = +e.target.value));
  $('#playBtn').addEventListener('click', () => {
    if (STATE.live && STATE.src.at >= STATE.live.source.t1 - 1) STATE.src.at = STATE.live.source.t0;
    REPLAY.playing = !REPLAY.playing; renderSourceBar();
  });
  let scrubT;
  $('#scrubRange').addEventListener('input', (e) => {
    const src = STATE.live && STATE.live.source; if (!src || src.kind !== 'replay') return;
    STATE.src.at = src.t0 + (+e.target.value / 1000) * src.length;
    $('#replayPos').textContent = `${mmss(STATE.src.at - src.t0)} of ${mmss(src.length)}`;
    clearTimeout(scrubT); scrubT = setTimeout(refreshAll, 120);
  });
  document.querySelectorAll('#modePick button').forEach((b) => b.addEventListener('click', () => {
    agentMode = b.dataset.mode;
    document.querySelectorAll('#modePick button').forEach((x) => x.setAttribute('aria-pressed', x === b));
  }));
  $('#agentStart').addEventListener('click', async () => {
    say('Starting the agent...');
    const r = await postJSON('/api/agent/start?mode=' + agentMode).catch(() => ({ message: 'The dashboard did not answer.' }));
    say(r.message, r.ok ? 'good' : 'bad');
    refreshAll();
  });
  $('#agentStop').addEventListener('click', async () => {
    say('Stopping the agent and undoing every slow-down...');
    const r = await postJSON('/api/agent/stop').catch(() => ({ message: 'The dashboard did not answer.' }));
    say(r.message, r.ok ? 'good' : 'bad');
    refreshAll();
  });
}

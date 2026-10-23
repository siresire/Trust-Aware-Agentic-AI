/* rules.js - edit the homeowner's rules (models/homeowner_policy.json).
   The server checks every value; the agent uses the new rules from its next start. */

const RULES = { saved: null, def: null, dirty: false };
const TELL_NAME = { jam: 'A jam', internet_fault: 'An internet fault', device_fault: 'A device fault' };

function toggle(id, label, checked, note = '') {
  return `<label class="switch"><input type="checkbox" id="${id}"${checked ? ' checked' : ''}><span class="knob" aria-hidden="true"></span>
    <span class="txt">${esc(label)}${note ? `<em>${esc(note)}</em>` : ''}</span></label>`;
}

function fillRules(p) {
  const d = RULES.def || p;
  $('#rMay').innerHTML = STATE.cfg.limitable.map((dev) => toggle('may-' + dev, dev, p.may_slow.includes(dev),
    d.may_slow.includes(dev) ? '' : 'not in the experiment')).join('');
  $('#rTell').innerHTML = Object.keys(TELL_NAME).map((k) => toggle('tell-' + k, TELL_NAME[k], p.tell_homeowner[k])).join('');
  $('#rImp').innerHTML = STATE.cfg.protected.map((dev) => `<div class="imp-row"><span>${esc(dev)}</span>
    <div class="seg small" role="group" aria-label="${esc(dev)} importance">${['high', 'medium', 'low'].map((lv) =>
      `<button type="button" data-dev="${dev}" data-lv="${lv}" aria-pressed="${p.protected[dev] === lv}">${lv}</button>`).join('')}</div></div>`).join('');
  $('#rRate').value = p.min_rate_mbit; $('#rMax').value = p.max_slow_s; $('#rCheck').value = p.recheck_every_s;
  $('#rImp').querySelectorAll('button').forEach((b) => b.addEventListener('click', () => {
    $('#rImp').querySelectorAll(`button[data-dev="${b.dataset.dev}"]`).forEach((x) => x.setAttribute('aria-pressed', x === b));
    markDirty();
  }));
}

function formRules() {
  const prot = {};
  $('#rImp').querySelectorAll('button[aria-pressed="true"]').forEach((b) => (prot[b.dataset.dev] = b.dataset.lv));
  return {
    may_slow: STATE.cfg.limitable.filter((d) => $('#may-' + d).checked),
    protected: prot,
    min_rate_mbit: +$('#rRate').value, max_slow_s: +$('#rMax').value, recheck_every_s: +$('#rCheck').value,
    tell_homeowner: Object.fromEntries(Object.keys(TELL_NAME).map((k) => [k, $('#tell-' + k).checked])),
  };
}

function rulesMsg(text, tone = '') { const m = $('#rMsg'); m.textContent = text; m.className = 'rules-msg ' + tone; }
function markDirty() { RULES.dirty = true; rulesMsg('Not saved yet.', 'warn'); }

function showState(st) {
  RULES.saved = st.policy; RULES.def = st.default;
  STATE.cfg.policy = st.policy;                 // the trust panel uses the new rules at once
  $('#rChanged').innerHTML = st.changed.length
    ? `<h2>Different from the experiment</h2><ul>${st.changed.map((c) => `<li>${esc(c)}</li>`).join('')}</ul>
       <p class="hint">Recorded runs and the Compare page always use the experiment's rules. These changes only affect new live runs.</p>`
    : '<h2>Same as the experiment</h2><p class="hint">These are the rules the recorded runs used.</p>';
}

async function loadRules() {
  try {
    const st = await getJSON('/api/policy');
    showState(st);
    if (!RULES.dirty) fillRules(st.policy);
  } catch (e) { rulesMsg('Could not read the rules from the dashboard.', 'bad'); }
}

function renderRulesStatus() {
  const running = !!agentNow() || (STATE.live && STATE.live.control && STATE.live.control.running);
  $('#rRestart').hidden = !(running && STATE.src.kind === 'live');
}

async function sendRules(path, body, done = 'Saved.') {
  const r = await postJSON(path, body).catch(() => ({ ok: false, errors: ['The dashboard did not answer.'] }));
  if (!r.ok) { rulesMsg(r.errors.join(' '), 'bad'); return; }
  RULES.dirty = false;
  showState(r); fillRules(r.policy);
  const running = r.agent && r.agent.running;
  rulesMsg(done + (running ? ' The running agent still uses the old rules: restart it to use these.' : ' The agent will use these rules the next time it starts.'), 'good');
  renderRulesStatus();
}

function setupRules() {
  const f = $('#rulesForm');
  f.addEventListener('input', markDirty);
  f.addEventListener('change', markDirty);
  f.addEventListener('submit', (e) => { e.preventDefault(); sendRules('/api/policy', formRules()); });
  $('#rUndo').addEventListener('click', () => { RULES.dirty = false; if (RULES.saved) fillRules(RULES.saved); rulesMsg(''); });
  $('#rReset').addEventListener('click', () => sendRules('/api/policy/reset', undefined, "Back to the experiment's rules."));
  $('#rRestart').addEventListener('click', async () => {
    const mode = (agentNow() && agentNow().mode) || agentMode;
    rulesMsg('Restarting the agent...');
    const r = await postJSON('/api/agent/restart?mode=' + mode).catch(() => ({ message: 'The dashboard did not answer.' }));
    rulesMsg(r.message, r.ok ? 'good' : 'bad');
  });
}

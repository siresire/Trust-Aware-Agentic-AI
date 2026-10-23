/* trust.js - the trust decision, step by step: what Agent 1 predicts, each check Agent 2 makes,
   and the final decision with its exact reason. The checks are worked out on the server
   (insights.trust_check) with the same rules as agent/agent2.py. */

const STATE_MARK = { pass: 'Yes', fail: 'No', ok: 'No', wait: 'Not yet', na: 'Not checked' };
const VERDICT_WORD = { ALLOW: 'Allow', DENY: 'Deny', 'NO ACTION': 'No action' };

const MSG_VERDICT = { right: 'right', partly: 'right device, plus others', wrong: 'wrong' };

function renderMessages() {
  const ms = ((STATE.live && STATE.live.messages) || []).slice().reverse();
  $('#tMsgs').innerHTML = ms.length ? ms.map((m) => `
    <li class="mv-${m.verdict}">
      <time>${clock(m.t)}</time>
      <div><b>${esc(m.text[0].toUpperCase() + m.text.slice(1))}</b>
        <span>Shown for ${Math.max(2, Math.round(m.until - m.t + 2))} s. Events log: ${esc(m.event)}, <em>${MSG_VERDICT[m.verdict]}</em>.</span></div>
    </li>`).join('') : '<li class="none">None yet. The agent tells the homeowner about faults, never about jams.</li>';
}

function renderTrust() {
  const box = $('#trust'); if (!box || !STATE.cfg) return;
  renderMessages();
  const a = agentNow(), thr = STATE.cfg.warn_prob;
  $('#tProbThr').textContent = `acts from ${thr.toFixed(2)}`;
  $('#tProbMark').style.left = thr * 100 + '%';
  if (!a) {
    box.dataset.verdict = 'none';
    $('#trust .verdict h2').textContent = 'Decision';
    $('#tProb').textContent = '–'; $('#tProbFill').style.width = '0';
    $('#tProposal').textContent = 'Agent not running'; $('#tProposalWhy').textContent = '';
    $('#tWarned').innerHTML = '';
    $('#tChecks').innerHTML = '<li class="empty">Start the agent, or replay a recorded run, to see the trust check work.</li>';
    $('#tVerdict').textContent = '–'; $('#tReason').textContent = ''; $('#tActed').textContent = '';
    $('#tTellBox').hidden = true; $('#tMode').textContent = '';
    return;
  }
  const d = a.decision, p = a.prob;
  box.dataset.verdict = d.verdict === 'ALLOW' ? 'allow' : d.verdict === 'DENY' ? 'deny' : 'calm';
  box.dataset.over = p >= thr ? 'yes' : 'no';
  $('#tProb').textContent = p.toFixed(2);
  $('#tProbFill').style.width = Math.min(100, p * 100) + '%';

  if (d.target) {
    const t = device(d.target), up = t && t.metrics ? kbps(t.metrics.tx_kbps) : '';
    $('#tProposal').textContent = `Slow the ${d.target}`;
    $('#tProposalWhy').textContent = `The biggest sender it may slow${up ? `, sending ${up} now` : ''}.`;
  } else {
    $('#tProposal').textContent = 'Nothing';
    $('#tProposalWhy').textContent = p < thr ? 'The warning is under the threshold.' : '';
  }
  const imp = STATE.cfg.policy.protected;
  const warned = (a.warned || []).slice().sort((x, y) => ['high', 'medium', 'low'].indexOf(imp[x]) - ['high', 'medium', 'low'].indexOf(imp[y]));
  $('#tWarned').innerHTML = warned.length
    ? warned.map((w) => `<li class="imp-${esc(imp[w])}"><span>${esc(w)}</span><em>${esc(imp[w])} importance</em></li>`).join('')
    : '<li class="none">None</li>';

  $('#tChecks').innerHTML = d.checks.map((c) => `
    <li data-state="${c.state}">
      <span class="ck-mark" aria-hidden="true"></span>
      <div class="ck-body">
        <span class="ck-title">${esc(c.title)}</span>
        <span class="ck-ans"><b>${STATE_MARK[c.state]}</b>${c.state === 'na' ? '' : ', ' + esc(c.value)}</span>
        <span class="ck-detail">${esc(c.state === 'na' ? c.value[0].toUpperCase() + c.value.slice(1) + '.' : c.detail)}</span>
      </div>
    </li>`).join('');

  $('#trust .verdict h2').textContent = a.mode === 'trust' ? 'Decision' : 'The trust check would say';
  $('#tVerdict').textContent = VERDICT_WORD[d.verdict] || d.verdict;
  $('#tReason').textContent = d.reason;
  $('#tActed').textContent = d.acted;
  $('#tTellBox').hidden = !d.tell;
  $('#tTell').textContent = d.tell ? d.tell[0].toUpperCase() + d.tell.slice(1) + '.' : '';
  $('#tMode').textContent = `${MODE_NAME[a.mode] || a.mode} agent. Snapshot at ${clock(a.t)}.`;
}

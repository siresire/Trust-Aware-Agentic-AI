/* decisions.js - the audit trail. One row per slow-down and per refusal: the prediction, the target,
   every trust check, the action, what the camera felt before and after, whether it was kept or undone,
   and what the events log says was really happening. */

const TRUTH = {
  right: ['Right', 'good'], handled: ['Right', 'good'], calm: ['Calm', 'plain'], waited: ['Waited', 'plain'],
  partly: ['Partly', 'warn'], wrong: ['Wrong', 'bad'], missed: ['Missed', 'bad'],
};
let decFilter = 'all', decOpen = null;

function decRow(r) {
  const i = r.t + ':' + r.kind;
  const t = TRUTH[r.truth] || [r.truth, 'plain'];
  const b = r.camera_before, a = r.camera_after;
  const cam = b ? `${num(b.rtt) ? fx(b.rtt) : '–'} → ${a && num(a.rtt) ? fx(a.rtt) + ' ms' : a ? 'no reply' : 'later'}` : '–';
  const verdict = r.kind === 'refuse' ? 'Deny' : r.agent2 === 'ALLOW' ? 'Allow' : r.agent2 === 'DENY' ? 'Deny' : r.agent2 || '–';
  const what = r.kind === 'refuse' ? r.action : r.action.replace(' to 2 Mbit/s', '');
  const len = r.kind === 'refuse' ? `${r.snapshots} snapshot${r.snapshots > 1 ? 's' : ''}` : (r.kept || '');
  return `<tr class="drow k-${r.kind}${decOpen === i ? ' open' : ''}" data-i="${i}" tabindex="0">
    <td class="tm">${clock(r.t)}</td>
    <td><span class="kind-tag ${r.kind}">${r.kind === 'refuse' ? 'Refused' : r.kind === 'slow' ? 'Slowed' : 'Blocked'}</span></td>
    <td class="num">${fx(r.prob, 2)}</td>
    <td>${esc(r.device || '–')}</td>
    <td>${pct(r.link)}, ${esc(r.diagnosis === 'ok' ? 'not steady yet' : r.diagnosis)}</td>
    <td><b class="vd ${verdict.toLowerCase()}">${esc(verdict)}</b>${r.mode === 'predict' && r.kind === 'slow' && r.agent2 !== 'ALLOW' ? '<span class="sub">ignored, no trust check</span>' : ''}</td>
    <td>${esc(what)}<span class="sub">${esc(len)}</span></td>
    <td class="num">${cam}<span class="sub cv-${(r.camera_verdict || '').replace(/ /g, '-')}">${esc(r.camera_verdict || '')}</span></td>
    <td><span class="truth ${t[1]}">${t[0]}</span><span class="sub">${esc(r.truth_text)}</span></td>
  </tr>` + (decOpen === i ? decDetail(r) : '');
}

function decDetail(r) {
  const checks = (r.checks || []).map((c) => `<li data-state="${c.state}"><span class="ck-mark"></span><div class="ck-body">
      <span class="ck-title">${esc(c.title)}</span><span class="ck-ans"><b>${STATE_MARK[c.state]}</b>${c.state === 'na' ? '' : ', ' + esc(c.value)}</span></div></li>`).join('');
  const w = (x) => (x ? `${num(x.rtt) ? fx(x.rtt) + ' ms' : 'no reply'}, loss ${fx(x.loss)}%, ${x.bad_pct}% bad (${x.n} readings)` : 'not measured yet');
  return `<tr class="ddetail"><td colspan="9"><div class="ddetail-grid">
    <div><h3>The trust check at ${clock(r.t)}</h3><ol class="checklist compact">${checks}</ol></div>
    <div><h3>Why and what</h3>
      <dl class="kv">
        <div><dt>Agent 2</dt><dd>${esc(r.agent2_reason || '–')}</dd></div>
        <div><dt>Why it acted now</dt><dd>${esc(r.kind === 'refuse' ? 'It did not: the trust check said no.' : r.why_now)}</dd></div>
        <div><dt>Action</dt><dd>${esc(r.action)}</dd></div>
        ${r.check ? `<div><dt>10-second check</dt><dd>${esc(r.check)}</dd></div>` : ''}
        ${r.kept ? `<div><dt>Kept or undone</dt><dd>${esc(r.kept)}</dd></div>` : ''}
        ${r.tell ? `<div><dt>Homeowner told</dt><dd>${esc(r.tell)}</dd></div>` : ''}
        <div><dt>Camera 6 s before</dt><dd>${w(r.camera_before)}</dd></div>
        <div><dt>Camera 10 to 20 s after</dt><dd>${w(r.camera_after)}</dd></div>
        <div><dt>Events log</dt><dd>${esc(r.truth_text)}</dd></div>
      </dl></div></div></td></tr>`;
}

function renderDecisions() {
  const d = STATE.decisions, tb = $('#audit'); if (!d || !tb) return;
  const rec = d.records.filter((r) => decFilter === 'all' || (decFilter === 'problem' ? ['wrong', 'missed', 'partly'].includes(r.truth) : r.kind === decFilter));
  const src = STATE.live && STATE.live.source;
  $('#decSub').textContent = `${MODE_NAME[d.mode] || 'Agent'} run${src && src.kind === 'replay' ? ` ${src.session}, up to ${mmss(src.elapsed)}` : ''}. ` +
    'Every slow-down and every refusal, with what the camera felt before and after. Newest first. Select a row to see every check.';
  const c = d.records.reduce((acc, r) => { acc[r.kind] = (acc[r.kind] || 0) + 1; acc[r.truth] = (acc[r.truth] || 0) + 1; return acc; }, {});
  $('#decCounts').innerHTML = [['Slow-downs', c.slow || 0], ['Refusals', c.refuse || 0],
    ['Wrong', (c.wrong || 0) + (c.partly || 0)], ['Missed', c.missed || 0]]
    .map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('');
  const q = srcQuery();
  $('#decCsv').href = '/api/export/decisions.csv' + (q ? '?' + q : '');
  $('#decJson').href = '/api/export/decisions.json' + (q ? '?' + q : '');
  if (!rec.length) {
    tb.innerHTML = `<tbody><tr><td class="empty">${d.records.length ? 'Nothing of this kind in this run.' : 'No decisions yet. The agent only decides when Agent 1 warns.'}</td></tr></tbody>`;
    return;
  }
  const shown = rec.slice(0, 400);
  tb.innerHTML = `<thead><tr><th>Time</th><th>What</th><th>Warning</th><th>Target</th><th>Line, problem</th><th>Trust check</th>
    <th>Action</th><th>Camera delay before → after</th><th>Events log says</th></tr></thead><tbody>` +
    shown.map(decRow).join('') + '</tbody>';
  tb.querySelectorAll('tr.drow').forEach((tr) => {
    const toggle = () => { const i = tr.dataset.i; decOpen = decOpen === i ? null : i; renderDecisions(); };
    tr.addEventListener('click', toggle);
    tr.addEventListener('keydown', (e) => { if (e.key === 'Enter') toggle(); });
  });
}

function setupDecisions() {
  document.querySelectorAll('#decFilter button').forEach((b) => b.addEventListener('click', () => {
    decFilter = b.dataset.f; decOpen = null;
    document.querySelectorAll('#decFilter button').forEach((x) => x.setAttribute('aria-pressed', x === b));
    renderDecisions();
  }));
}

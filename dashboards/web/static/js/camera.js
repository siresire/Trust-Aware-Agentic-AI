/* camera.js - the camera, the protected device the paper follows: its delay and loss against its
   own normal, the events (from the events log) and the agent's actions on one timeline, and whether
   the last slow-down actually helped it. */

const CAM_VERDICT = { better: 'It helped the camera', worse: 'The camera got worse', 'no better': 'No better for the camera',
  'was already fine': 'The camera was already fine', 'not measured yet': 'Too soon to tell' };

function eventSpans(events, now) {
  return (events || []).map((e) => ({
    a: e.start, b: e.end || now, cls: e.type.startsWith('C_') ? 'span-jam' : 'span-fault',
    label: `${e.type} on ${e.devices.join(', ')}${e.end ? '' : ' (running)'}`,
  }));
}

function camWin(w) {
  if (!w) return '<td>–</td><td>–</td><td>–</td>';
  return `<td>${num(w.rtt) ? fx(w.rtt) + ' ms' : 'no reply'}</td><td>${fx(w.loss)}%</td><td>${w.bad_pct}%</td>`;
}

function renderCamera() {
  const c = STATE.camera, box = $('#camChart'); if (!c || !box) return;
  const m = c.latest || {}, n = c.normal_ms, lm = c.last_minute;
  const rtt = m.rtt_ms;
  $('#camRtt').textContent = num(rtt) ? `${fx(rtt)} ms` : m.timestamp ? 'no reply' : '–';
  $('#camRtt').className = !num(rtt) && m.timestamp ? 'bad' : rtt >= 2 * n ? 'bad' : rtt > n ? 'over' : '';
  $('#camRttSub').textContent = `normal up to ${fx(n)} ms`;
  $('#camLoss').textContent = lm ? `${fx(lm.loss)}%` : '–';
  $('#camLoss').className = lm && lm.loss > 0 ? 'bad' : '';
  $('#camLossSub').textContent = lm ? `${lm.bad_pct}% of readings slow or lost` : '';

  const t1 = c.now, t0 = t1 - 600;
  const marks = c.actions.filter((a) => a.event !== 'CHECK').map((a) => ({
    t: a.t, cls: a.event === 'SLOW' ? 'slow' : 'undo',
    label: a.event === 'SLOW' ? `Slowed the ${a.device}` : `Gave the ${a.device} its speed back`,
  }));
  timeChart(box, {
    label: 'Camera delay', t0, t1, height: 210, spans: eventSpans(c.events, t1), marks,
    series: [{ name: 'Delay', color: 'var(--ok)', data: c.series.map((r) => [r[0], r[1]]), fmt: (v) => fx(v) + ' ms' }],
    bars: { name: 'Ping loss', data: c.series.map((r) => [r[0], r[2]]), max: 100, color: 'var(--jam)', h: 30, fmt: (v) => fx(v) + '%' },
    guides: [{ v: n, color: 'var(--ink-2)', label: 'normal' }, { v: 2 * n, color: 'var(--jam)', label: 'twice normal' }],
    ymax: Math.max(3 * n, ...c.series.map((r) => r[1] || 0)) * 1.05, yfmt: (v) => Math.round(v),
    empty: 'No camera readings in the last 10 minutes',
  });

  const s = c.last_slow, out = $('#camLast');
  if (!s) {
    out.innerHTML = '<p class="note">No slow-down yet in this run, so there is no before and after to show.</p>';
    return;
  }
  const ev = s.event ? `during ${s.event.type} by ${s.event.devices.join(', ')}` : 'with no event running';
  out.innerHTML = `
    <div class="camlast-head">
      <span class="who">Last slow-down</span>
      <strong>The ${esc(s.device)} at ${clock(s.t)}, ${esc(ev)}</strong>
    </div>
    <table class="beforeafter">
      <thead><tr><th></th><th>Delay</th><th>Loss</th><th>Bad readings</th></tr></thead>
      <tbody>
        <tr><th>6 s before</th>${camWin(s.camera_before)}</tr>
        <tr><th>10 to 20 s after</th>${camWin(s.camera_after)}</tr>
      </tbody>
    </table>
    <p class="cam-verdict v-${esc(s.camera_verdict.replace(/ /g, '-'))}">${esc(CAM_VERDICT[s.camera_verdict] || s.camera_verdict)}.
      <span>${esc(s.check ? 'Agent check ' + s.check + '. ' : '')}${esc(s.kept ? s.kept[0].toUpperCase() + s.kept.slice(1) + '.' : '')}</span></p>`;
}

/* chart.js - one small SVG time chart with guide lines, shaded spans and a hover read-out.
   timeChart(box, {series:[{data:[[t,v]], color, name, fmt}], t0, t1, ymax, guides:[{v,color,label}],
                   spans:[{a,b,cls}], height, yfmt}) */

function timeChart(box, o) {
  const W = Math.max(280, box.clientWidth), H = o.height || 200;
  const P = { l: 46, r: 12, t: 12, b: 24 }, iw = W - P.l - P.r, ih = H - P.t - P.b;
  const all = o.series.flatMap((s) => s.data.filter((p) => num(p[1])));
  box.innerHTML = '';
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, height: H, role: 'img', 'aria-label': o.label || 'chart' }, box);
  if (!all.length) {
    el('text', { x: W / 2, y: H / 2, 'text-anchor': 'middle' }, svg).textContent = o.empty || 'No readings yet';
    return;
  }
  const t1 = o.t1 || Math.max(...all.map((p) => p[0])), t0 = o.t0 || Math.min(...all.map((p) => p[0]));
  const top = o.ymax || Math.max(...all.map((p) => p[1]), ...(o.guides || []).map((g) => g.v), o.ymin || 1) * 1.12;
  const X = (t) => P.l + ((t - t0) / Math.max(1, t1 - t0)) * iw;
  const Y = (v) => P.t + ih - (Math.min(v, top) / top) * ih;
  const yf = o.yfmt || ((v) => (v >= 100 ? Math.round(v) : v.toFixed(v < 10 ? 1 : 0)));

  for (const s of o.spans || []) {
    const a = Math.max(t0, s.a), b = Math.min(t1, s.b);
    if (b > a) el('rect', { class: s.cls, x: X(a), y: P.t, width: Math.max(2, X(b) - X(a)), height: ih }, svg);
  }
  for (let i = 0; i <= 3; i++) {
    const v = (top / 3) * i, y = Y(v);
    el('line', { class: 'grid', x1: P.l, x2: W - P.r, y1: y, y2: y }, svg);
    el('text', { x: P.l - 8, y: y + 4, 'text-anchor': 'end' }, svg).textContent = yf(v);
  }
  for (const g of o.guides || []) {
    if (g.v > top) continue;
    el('line', { class: 'guide', x1: P.l, x2: W - P.r, y1: Y(g.v), y2: Y(g.v), stroke: g.color }, svg);
    el('text', { x: W - P.r, y: Y(g.v) - 5, 'text-anchor': 'end', fill: g.color }, svg).textContent = g.label;
  }
  for (const s of o.series) {
    let d = '', prev = null;
    for (const p of s.data) {
      if (!num(p[1]) || p[0] < t0) { prev = null; continue; }
      d += (prev === null || p[0] - prev > 8 ? 'M' : 'L') + X(p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1);
      prev = p[0];
    }
    el('path', { class: 'series', d, stroke: s.color }, svg);
    for (const p of s.data) if (!num(p[1]) && p[0] >= t0) el('circle', { cx: X(p[0]), cy: P.t + 6, r: 3, fill: 'var(--jam)' }, svg);
  }
  // bars along the bottom (e.g. ping loss), scaled to their own max
  if (o.bars) {
    const bh = o.bars.h || 26, bw = Math.max(2, iw / Math.max(60, (t1 - t0) / 2) - 1);
    for (const p of o.bars.data) {
      if (!num(p[1]) || p[1] <= 0 || p[0] < t0) continue;
      const h = Math.max(3, (Math.min(p[1], o.bars.max) / o.bars.max) * bh);
      el('rect', { class: 'bar-mark', x: X(p[0]) - bw / 2, y: P.t + ih - h, width: bw, height: h, fill: o.bars.color }, svg);
    }
  }
  // action markers: a small flag at the top and a thin line down
  for (const m of o.marks || []) {
    if (m.t < t0 || m.t > t1) continue;
    el('line', { class: 'mark-line ' + (m.cls || ''), x1: X(m.t), x2: X(m.t), y1: P.t, y2: P.t + ih }, svg);
    el('path', { class: 'mark-flag ' + (m.cls || ''), d: `M${X(m.t) - 5} ${P.t} L${X(m.t) + 5} ${P.t} L${X(m.t)} ${P.t + 7} Z` }, svg);
  }
  const ticks = W > 600 ? 4 : 2;
  for (let i = 0; i <= ticks; i++) {
    const t = t0 + ((t1 - t0) * i) / ticks;
    el('text', { x: X(t), y: H - 6, 'text-anchor': i === 0 ? 'start' : i === ticks ? 'end' : 'middle' }, svg).textContent = clock(t).slice(0, 5);
  }
  const cursor = el('line', { class: 'cursor', x1: -9, x2: -9, y1: P.t, y2: P.t + ih }, svg);
  svg.addEventListener('mousemove', (e) => {
    const r = svg.getBoundingClientRect(), px = ((e.clientX - r.left) / r.width) * W;
    if (px < P.l || px > W - P.r) { hideTip(); return; }
    const t = t0 + ((px - P.l) / iw) * (t1 - t0);
    let html = `<b>${clock(t)}</b>`;
    for (const s of o.series) {
      let best = null;
      for (const p of s.data) if (!best || Math.abs(p[0] - t) < Math.abs(best[0] - t)) best = p;
      if (best) html += tipRow(s.name, num(best[1]) ? s.fmt(best[1]) : 'no reply');
      if (best && o.bars) { const b = o.bars.data.find((p) => p[0] === best[0]); if (b) html += tipRow(o.bars.name, o.bars.fmt(b[1])); }
      for (const sp of o.spans || []) if (sp.label && t >= sp.a && t <= sp.b) { html += `<div class="row"><span>${esc(sp.label)}</span></div>`; break; }
      for (const m of o.marks || []) if (Math.abs(m.t - t) < (t1 - t0) / 120 && m.label) html += `<div class="row"><span>${esc(m.label)}</span></div>`;
      if (best) { cursor.setAttribute('x1', X(best[0])); cursor.setAttribute('x2', X(best[0])); }
    }
    showTip(html, e.clientX, e.clientY);
  });
  svg.addEventListener('mouseleave', () => { hideTip(); cursor.setAttribute('x1', -9); cursor.setAttribute('x2', -9); });
}

/* xyChart: numbers on both axes (threshold sweep, calibration).
   o = {series:[{data:[[x,y]], color, name, fmt, right, dots}], xmin, xmax, ymax, y2max, height,
        xfmt, yfmt, y2fmt, vline:{x,label}, diagonal, xlabel} */
function xyChart(box, o) {
  const W = Math.max(280, box.clientWidth), H = o.height || 240;
  const P = { l: 46, r: o.y2max ? 46 : 14, t: 14, b: 38 }, iw = W - P.l - P.r, ih = H - P.t - P.b;
  box.innerHTML = '';
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, height: H, role: 'img', 'aria-label': o.label || 'chart' }, box);
  const x0 = o.xmin ?? 0, x1 = o.xmax ?? 1, ym = o.ymax ?? 1, y2m = o.y2max || 1;
  const X = (x) => P.l + ((x - x0) / (x1 - x0)) * iw;
  const Y = (y, right) => P.t + ih - (Math.max(0, Math.min(y, right ? y2m : ym)) / (right ? y2m : ym)) * ih;
  const xf = o.xfmt || ((v) => v.toFixed(1)), yf = o.yfmt || ((v) => v), y2f = o.y2fmt || ((v) => v);
  for (let i = 0; i <= 4; i++) {
    const y = P.t + ih - (ih * i) / 4;
    el('line', { class: 'grid', x1: P.l, x2: W - P.r, y1: y, y2: y }, svg);
    el('text', { x: P.l - 8, y: y + 4, 'text-anchor': 'end' }, svg).textContent = yf((ym * i) / 4);
    if (o.y2max) el('text', { x: W - P.r + 8, y: y + 4, 'text-anchor': 'start' }, svg).textContent = y2f((y2m * i) / 4);
  }
  for (let i = 0; i <= 5; i++) {
    const x = x0 + ((x1 - x0) * i) / 5;
    el('text', { x: X(x), y: H - 20, 'text-anchor': 'middle' }, svg).textContent = xf(x);
  }
  if (o.xlabel) el('text', { x: P.l + iw / 2, y: H - 4, 'text-anchor': 'middle', class: 'axis-label' }, svg).textContent = o.xlabel;
  if (o.diagonal) el('line', { class: 'guide', x1: X(x0), y1: Y(0), x2: X(x1), y2: Y(ym), stroke: 'var(--ink-3)' }, svg);
  if (o.vline) {
    el('line', { class: 'vline', x1: X(o.vline.x), x2: X(o.vline.x), y1: P.t, y2: P.t + ih }, svg);
    el('text', { x: X(o.vline.x) + 5, y: P.t + ih - 6, class: 'vline-label' }, svg).textContent = o.vline.label;
  }
  for (const s of o.series) {
    const pts = s.data.filter((p) => num(p[0]) && num(p[1]));
    el('path', { class: 'series', stroke: s.color, d: pts.map((p, i) => (i ? 'L' : 'M') + X(p[0]).toFixed(1) + ' ' + Y(p[1], s.right).toFixed(1)).join('') }, svg);
    if (s.dots) for (const p of pts) el('circle', { cx: X(p[0]), cy: Y(p[1], s.right), r: p[2] ? Math.max(2.5, Math.min(9, Math.sqrt(p[2]) / 3)) : 3.5, fill: s.color, 'fill-opacity': .85 }, svg);
  }
  const cursor = el('line', { class: 'cursor', x1: -9, x2: -9, y1: P.t, y2: P.t + ih }, svg);
  svg.addEventListener('mousemove', (e) => {
    const r = svg.getBoundingClientRect(), px = ((e.clientX - r.left) / r.width) * W;
    if (px < P.l || px > W - P.r) { hideTip(); return; }
    const x = x0 + ((px - P.l) / iw) * (x1 - x0);
    let html = '';
    for (const s of o.series) {
      let best = null;
      for (const p of s.data) if (num(p[1]) && (!best || Math.abs(p[0] - x) < Math.abs(best[0] - x))) best = p;
      if (best) { html += tipRow(s.name, s.fmt(best[1], best)); if (!html.startsWith('<b>')) html = `<b>${o.tipx ? o.tipx(best[0]) : xf(best[0])}</b>` + html; cursor.setAttribute('x1', X(best[0])); cursor.setAttribute('x2', X(best[0])); }
    }
    showTip(html, e.clientX, e.clientY);
  });
  svg.addEventListener('mouseleave', () => { hideTip(); cursor.setAttribute('x1', -9); cursor.setAttribute('x2', -9); });
}

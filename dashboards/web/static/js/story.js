/* story.js - turns the agent's newest snapshot into plain sentences: the headline and the last decision. */

const MODE_TEXT = {
  trust: 'Trust-aware agent, checking every 2 seconds',
  predict: 'Prediction-only agent: acts on every warning, no trust check',
  none: 'Agent in watch-only mode: it never slows anything',
};

function deviceList(names) { return list(names.map((n) => 'the ' + n)); }

/* one short line for the situation, said by the robot */
function storyFor(a, live) {
  const s = live.summary;
  if (!live.logs_found || !s.online) return { tone: 'idle', line: 'The network is not running.' };
  if (!a) return { tone: (s.critical + s.warning) ? 'watch' : 'idle', line: 'The agent is not running. Press Start agent.' };
  const slowed = a.slowed || [], target = a.a1.startsWith('slow') ? a.a1.slice(5) : '';
  const faulty = a.steady === 'internet fault' || a.steady === 'device fault';
  if (a.steady === 'jam' && a.mode === 'none') return { tone: 'jam', line: 'The line is jammed. Watch-only mode, so I do nothing.' };
  if (a.steady === 'jam') return { tone: 'jam', line: slowed.length ? `The line is jammed. Slowing the ${list(slowed)}.` : 'The line is jammed. Acting now.' };
  if (faulty && a.mode === 'predict' && target) return { tone: 'fault', line: `A fault, not a jam. No trust check, so the ${target} gets slowed anyway.` };
  if (a.steady === 'internet fault') return { tone: 'fault', line: 'The internet connection has a problem. Slowing will not help.' };
  if (a.steady === 'device fault') {
    const who = (a.tell.split(' on ')[1] || '').split(',').filter(Boolean);
    return { tone: 'fault', line: who.length ? `The ${list(who)} ${who.length > 1 ? 'have' : 'has'} a bad connection. Nothing slowed.` : 'One device has a bad connection. Nothing slowed.' };
  }
  if (a.now !== 'ok') return { tone: 'watch', line: 'Something looks off. The agent is watching before it decides.' };
  if (slowed.length) return { tone: 'calm', line: `Jam cleared. The ${list(slowed)} gets its speed back soon.` };
  return { tone: 'calm', line: 'All calm.' };
}

/* type the new line letter by letter while the robot's mouth moves */
let lastLine = '', typing = null;
function robotSay(line) {
  const p = $('#storyHead'), box = $('#story');
  clearInterval(typing);
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) { p.textContent = line; return; }
  let i = 0;
  box.classList.add('talking');
  p.textContent = '';
  typing = setInterval(() => {
    i += 1;
    p.textContent = line.slice(0, i);
    if (i >= line.length) { clearInterval(typing); box.classList.remove('talking'); }
  }, 28);
}

function renderStory() {
  const live = STATE.live; if (!live) return;
  const st = storyFor(agentNow(), live), box = $('#story');
  box.dataset.tone = st.tone;
  if (st.line !== lastLine) { lastLine = st.line; robotSay(st.line); }
}

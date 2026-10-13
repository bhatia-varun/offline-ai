const demos = [
  {key:'streamlit',name:'Streamlit · Chat, RAG & Tools',port:8501},
  {key:'webui',name:'Open WebUI · Chat client',port:3000},
  {key:'n8n',name:'n8n · Workflow automation',port:5678},
  {key:'comfy',name:'ComfyUI · Image generation',port:8188}
];
const $ = id => document.getElementById(id);
let status = {}, index = -1, running = false, paused = false, remaining = 15, lastTick = 0, autoPending = false;
const ready = i => status[demos[i].key]?.phase === 'ready';
const feedback = text => $('feedback').textContent = text;
const duration = () => Number($('delay').value);
function render() {
  $('services').replaceChildren(...demos.map((demo,i) => {
    const button = document.createElement('button');
    button.className = 'service' + (i === index ? ' active' : '');
    const label = document.createElement('span'); label.textContent = demo.name;
    const dot = document.createElement('span'); dot.className = 'dot ' + (status[demo.key]?.phase || 'idle');
    button.append(label,dot); button.onclick = () => select(i);
    return button;
  }));
  $('detail').textContent = index < 0 ? 'Select a station to preview it. Services launch sequentially; errors won’t block the next station.' :
    `${demos[index].name}: ${status[demos[index].key]?.message || status[demos[index].key]?.phase || 'Not started'}`;
  $('pause').textContent = paused ? 'Resume tour' : 'Pause tour';
  $('countdown').textContent = running ? paused ? 'Tour paused' : `${Math.ceil(remaining)}s until next demo` : 'Tour idle';
}
function select(i) {
  index = i; remaining = duration(); lastTick = performance.now();
  const demo = demos[i]; $('title').textContent = demo.name;
  const url = `http://127.0.0.1:${demo.port}/`;
  $('external').href = url; $('external').hidden = false;
  const frame = document.createElement('iframe'); frame.title = demo.name; frame.src = url;
  const viewer = $('viewer'); viewer.replaceChildren();
  if (ready(i)) viewer.append(frame);
  else { const place = document.createElement('div'); place.className = 'placeholder'; place.textContent = `${demo.name} is not ready yet. Use Open in new tab or wait for startup.`; viewer.append(place); }
  render();
}
function move(step) {
  let next = index;
  for (let n=0;n<demos.length;n++) {
    next = (next+step+demos.length)%demos.length;
    if (ready(next) && next !== index) { select(next); return true; }
  }
  if (index >= 0 && ready(index)) {
    remaining = duration();
    feedback('Only one demo is ready. Staying on this station.');
    return false;
  }
  feedback('No demos are ready yet. Check the service indicators.'); return false;
}
function beginTour() {
  if (!demos.some((_,i) => ready(i))) { feedback('Waiting for a demo to become ready…'); autoPending = true; return; }
  autoPending = false; running = true; paused = false; remaining = duration(); lastTick = performance.now();
  select(demos.findIndex((_,i) => ready(i))); feedback('Guided tour running. Pause anytime to explore a demo.');
}
async function refresh() {
  try {
    const response = await fetch('/api/status');
    if (!response.ok) throw Error('Status unavailable');
    const data = await response.json(); status = data.services;
    if (autoPending && demos.some((_,i) => ready(i))) beginTour();
    else if (autoPending && !data.launching) { autoPending = false; feedback('Startup finished, but no demo is ready. Check the station messages and logs.'); }
    else if (index >= 0 && ready(index) && !$('viewer').querySelector('iframe')) select(index);
    render();
  } catch { feedback('Dashboard status unavailable. Refresh the page.'); }
}
async function start() {
  autoPending = true; feedback('Launching services. The tour begins when the first demo is ready…');
  try {
    const response = await fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    if (!response.ok) throw Error('Launcher rejected request');
    await refresh();
  } catch (err) { autoPending = false; feedback(err.message); }
}
$('start').onclick = start;
$('tour').onclick = beginTour;
$('previous').onclick = () => move(-1);
$('next').onclick = () => move(1);
$('pause').onclick = () => { if (!running) { beginTour(); return; } paused = !paused; lastTick = performance.now(); render(); };
$('delay').oninput = () => { $('delayValue').value = `${duration()}s`; remaining = duration(); render(); };
setInterval(() => {
  const now = performance.now();
  if (running && !paused && !document.hidden) { remaining -= Math.min((now-lastTick)/1000,1); if (remaining <= 0) move(1); }
  lastTick = now; render();
},250);
setInterval(refresh,2500);
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (!SpeechRecognition) { $('mic').disabled = true; $('mic').title = 'Speech recognition is not supported in this browser'; }
else $('mic').onclick = () => {
  const recognition = new SpeechRecognition(); recognition.lang = 'en-US'; recognition.continuous = false;
  $('mic').classList.add('listening'); feedback('Listening… say “Jarvis start demo”.');
  recognition.onresult = event => {
    const words = event.results[0][0].transcript.toLowerCase();
    if (/jarvis.*start.*demo/.test(words)) start();
    else if (/jarvis.*pause/.test(words)) { if (running && !paused) $('pause').click(); }
    else if (/jarvis.*(resume|continue)/.test(words)) { if (paused) $('pause').click(); }
    else feedback(`Heard “${words}”. Try “Jarvis start demo”.`);
  };
  recognition.onerror = event => feedback(`Microphone: ${event.error}. Use the button if speech recognition is unavailable.`);
  recognition.onend = () => $('mic').classList.remove('listening');
  try { recognition.start(); } catch { $('mic').classList.remove('listening'); feedback('Could not start speech recognition. Use the launch button.'); }
};
refresh();

"""Browser-only microphone or explicitly shared-tab capture; local chunked Whisper."""

import streamlit as st

HTML = """
<div>
  <label for="source">Live source:</label>
  <select id="source"><option value="mic">Microphone / selected input device</option><option value="tab">Share browser tab with audio</option></select>
  <button id="start">Start live transcription</button>
  <button id="stop" disabled>Stop</button>
  <p id="status" role="status">Stopped. Audio stays on this machine.</p>
  <div id="transcript" aria-live="polite" style="white-space:pre-wrap"></div>
</div>
"""

JS = r"""
export default function(component) {
  const root = component.parentElement;
  const source = root.querySelector('#source');
  const start = root.querySelector('#start');
  const stop = root.querySelector('#stop');
  const status = root.querySelector('#status');
  const transcript = root.querySelector('#transcript');
  const endpoint = 'http://127.0.0.1:8000/audio/transcribe';
  let stream, context, input, processor, silent, timer;
  let active = false, busy = false, samples = [], queued = 0, seconds = 0, generation = 0;
  let unmounted = false;
  const SAMPLE_RATE = 16000, CHUNK_SECONDS = 4, MAX_SECONDS = 120;
  const say = (text) => { status.textContent = text; };
  function release() {
    active = false;
    clearInterval(timer);
    if (processor) processor.disconnect();
    if (input) input.disconnect();
    if (silent) silent.disconnect();
    if (stream) stream.getTracks().forEach(track => track.stop());
    if (context) context.close().catch(() => {});
    samples = []; queued = 0;
    processor = input = silent = stream = context = null;
    start.disabled = busy;
    stop.disabled = true;
    source.disabled = false;
  }
  function wav(parts) {
    const n = parts.reduce((sum, part) => sum + part.length, 0);
    const buffer = new ArrayBuffer(44 + n * 2);
    const view = new DataView(buffer);
    const fourcc = (offset, word) => { for (let i = 0; i < 4; i++) view.setUint8(offset + i, word.charCodeAt(i)); };
    fourcc(0, 'RIFF'); view.setUint32(4, 36 + n * 2, true); fourcc(8, 'WAVE');
    fourcc(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
    view.setUint16(22, 1, true); view.setUint32(24, SAMPLE_RATE, true);
    view.setUint32(28, SAMPLE_RATE * 2, true); view.setUint16(32, 2, true);
    view.setUint16(34, 16, true); fourcc(36, 'data'); view.setUint32(40, n * 2, true);
    let offset = 44;
    for (const part of parts) for (const sample of part) {
      const value = Math.max(-1, Math.min(1, sample));
      view.setInt16(offset, value < 0 ? value * 32768 : value * 32767, true);
      offset += 2;
    }
    return buffer;
  }
  function resample(buffer, rate) {
    if (rate === SAMPLE_RATE) return buffer;
    const length = Math.floor(buffer.length * SAMPLE_RATE / rate);
    const output = new Float32Array(length);
    for (let i = 0; i < length; i++) {
      const index = i * rate / SAMPLE_RATE;
      const j = Math.floor(index);
      const fraction = index - j;
      output[i] = buffer[j] * (1 - fraction) + buffer[Math.min(j + 1, buffer.length - 1)] * fraction;
    }
    return output;
  }
  async function send(parts) {
    busy = true;
    const thisGeneration = generation;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 100000);
    try {
      say('Transcribing the latest audio chunk locally...');
      const response = await fetch(endpoint, {
        method: 'POST', headers: {'Content-Type': 'audio/wav'},
        body: wav(parts), signal: controller.signal,
      });
      const result = await response.json();
      if (!response.ok) throw Error(result.detail || 'Transcription failed');
      if (thisGeneration === generation) {
        if (result.text) transcript.textContent += (transcript.textContent ? ' ' : '') + result.text;
        say(active ? 'Listening; transcript updates after each ~4-second chunk.' : 'Stopped.');
      }
    } catch (error) {
      if (thisGeneration === generation) say('Transcription failed: ' + error.message);
    } finally {
      clearTimeout(timeout);
      busy = false;
      if (unmounted) return;
      if (!active) start.disabled = false;
      else if (queued >= CHUNK_SECONDS * SAMPLE_RATE) flush();
    }
  }
  function flush(force = false) {
    if (busy || !samples.length || (!force && queued < CHUNK_SECONDS * SAMPLE_RATE)) return;
    const parts = samples;
    samples = [];
    queued = 0;
    void send(parts);
  }
  async function begin() {
    if (busy) { say('Wait for the last audio chunk to finish transcribing.'); return; }
    start.disabled = true;
    try {
      const sharing = source.value === 'tab';
      if (sharing && !navigator.mediaDevices.getDisplayMedia) throw Error('Tab audio sharing is unavailable in this browser.');
      stream = sharing
        ? await navigator.mediaDevices.getDisplayMedia({video: true, audio: true})
        : await navigator.mediaDevices.getUserMedia({audio: true});
      if (!stream.getAudioTracks().length) throw Error('No audio track shared. Select a browser tab and enable Share tab audio.');
      context = new AudioContext();
      await context.resume();
      input = context.createMediaStreamSource(stream);
      processor = context.createScriptProcessor(4096, 1, 1);
      silent = context.createGain(); silent.gain.value = 0;
      input.connect(processor); processor.connect(silent); silent.connect(context.destination);
      generation++;
      transcript.textContent = ''; samples = []; queued = seconds = 0;
      active = true;
      processor.onaudioprocess = (event) => {
        if (!active) return;
        // Keep a bounded buffer while MLX is busy; never queue minutes of audio.
        if (busy && queued >= CHUNK_SECONDS * SAMPLE_RATE) return;
        const chunk = resample(event.inputBuffer.getChannelData(0), context.sampleRate);
        samples.push(chunk); queued += chunk.length;
        if (queued >= CHUNK_SECONDS * SAMPLE_RATE) flush();
      };
      stream.getTracks().forEach(track => track.addEventListener('ended', () => { if (active) end(); }));
      source.disabled = true; stop.disabled = false;
      say(sharing ? 'Listening to explicitly shared tab audio.' : 'Listening to microphone / selected input.');
      timer = setInterval(() => {
        if (!active) return;
        seconds++;
        if (seconds >= MAX_SECONDS) end();
        else flush();
      }, 1000);
    } catch (error) {
      release(); say('Could not start: ' + error.message);
    }
  }
  function end() {
    if (!active) return;
    active = false;
    clearInterval(timer);
    if (processor) processor.onaudioprocess = null;
    const skipped = busy && queued > 0;
    if (!busy) flush(true);
    release();
    if (skipped) say('Stopped; final partial chunk was skipped while the model was busy.');
    else if (!busy) say('Stopped.');
  }
  start.addEventListener('click', begin);
  stop.addEventListener('click', end);
  return () => { unmounted = true; generation++; release(); };
}
"""

live_audio = st.components.v2.component("offline_live_audio", html=HTML, js=JS)

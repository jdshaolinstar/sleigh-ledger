// Tiny synthesized sound effects (Web Audio, no files). Browsers only allow audio after a click,
// so the context starts on the first user gesture.
let ctx = null;
let muted = false;
try { muted = localStorage.getItem("sl-muted") === "1"; } catch (e) { /* storage blocked */ }

function ac() {
  if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
  if (ctx.state === "suspended") ctx.resume();
  return ctx;
}
addEventListener("pointerdown", () => { try { ac(); } catch (e) { /* no audio */ } }, { once: true });

function tone(freq, start, dur, { type = "sine", vol = 0.12, slide = 0 } = {}) {
  const a = ac(), o = a.createOscillator(), g = a.createGain();
  o.type = type;
  o.frequency.setValueAtTime(freq, a.currentTime + start);
  if (slide) o.frequency.exponentialRampToValueAtTime(Math.max(40, freq + slide), a.currentTime + start + dur);
  g.gain.setValueAtTime(0.0001, a.currentTime + start);
  g.gain.exponentialRampToValueAtTime(vol, a.currentTime + start + 0.015);
  g.gain.exponentialRampToValueAtTime(0.0001, a.currentTime + start + dur);
  o.connect(g).connect(a.destination);
  o.start(a.currentTime + start);
  o.stop(a.currentTime + start + dur + 0.05);
}

const play = (fn) => { if (muted) return; try { fn(); } catch (e) { /* audio unavailable */ } };

export const sfx = {
  // bright sleigh-bell style arpeggio
  buy: () => play(() => { [1047, 1319, 1568, 2093].forEach((f, i) => tone(f, i * 0.07, 0.35, { type: "triangle", vol: 0.1 })); tone(3136, 0.3, 0.25, { vol: 0.05 }); }),
  // waiting for a parent: two soft questioning notes
  pending: () => play(() => { tone(784, 0, 0.18, { type: "triangle" }); tone(988, 0.16, 0.28, { type: "triangle" }); }),
  // blocked: cartoon "bonk"
  blocked: () => play(() => { tone(220, 0, 0.22, { type: "square", vol: 0.07, slide: -110 }); tone(165, 0.12, 0.25, { type: "square", vol: 0.05, slide: -60 }); }),
  // shop sign revealed: sparkle
  reveal: () => play(() => { [1568, 2093, 2637].forEach((f, i) => tone(f, i * 0.05, 0.2, { vol: 0.05 })); }),
  // clicked an elf: "boop"
  boop: () => play(() => tone(520, 0, 0.16, { type: "sine", vol: 0.14, slide: 260 })),
  // UI buttons
  tick: () => play(() => tone(1200, 0, 0.05, { type: "square", vol: 0.03 })),
  // Persona verified / pot unlocked: happy chord
  unlock: () => play(() => { [523, 659, 784, 1047].forEach((f) => tone(f, 0, 0.6, { type: "triangle", vol: 0.06 })); }),
  // footstep patter when an elf sets off
  step: () => play(() => { for (let i = 0; i < 3; i++) tone(300 + Math.random() * 60, i * 0.11, 0.04, { type: "square", vol: 0.02 }); }),
  isMuted: () => muted,
  toggle: () => { muted = !muted; try { localStorage.setItem("sl-muted", muted ? "1" : "0"); } catch (e) { /* ignore */ } return muted; },
};

// ---------------------------------------------------------------- music box "Jingle Bells"
// Melody: James Lord Pierpont, 1857 (public domain). Synthesized here; no audio files.
const N = { C3: 130.81, F3: 174.61, G3: 196.0, C5: 523.25, D5: 587.33, E5: 659.25, F5: 698.46, G5: 783.99 };
const A = [["E5", 1], ["E5", 1], ["E5", 2], ["E5", 1], ["E5", 1], ["E5", 2], ["E5", 1], ["G5", 1], ["C5", 1.5], ["D5", 0.5], ["E5", 4]];
const B = [["F5", 1], ["F5", 1], ["F5", 1.5], ["F5", 0.5], ["F5", 1], ["E5", 1], ["E5", 1], ["E5", 0.5], ["E5", 0.5], ["E5", 1], ["D5", 1], ["D5", 1], ["E5", 1], ["D5", 2], ["G5", 2]];
const C = [["F5", 1], ["F5", 1], ["F5", 1.5], ["F5", 0.5], ["F5", 1], ["E5", 1], ["E5", 1], ["E5", 0.5], ["E5", 0.5], ["G5", 1], ["G5", 1], ["F5", 1], ["D5", 1], ["C5", 4]];
const MELODY = [...A, ...B, ...A, ...C];
const BARS = ["C3", "C3", "C3", "C3", "F3", "C3", "G3", "G3", "C3", "C3", "C3", "C3", "F3", "C3", "G3", "C3"]; // one root per 4-beat bar
const BEAT = 60 / 128;
let musicOn = true;
try { musicOn = localStorage.getItem("sl-music") !== "0"; } catch (e) { /* ignore */ }
let musicTimer = null, nextTime = 0, idx = 0, beatPos = 0;

function musicNote(freq, t, dur, vol, type = "triangle") {
  const a = ac(), o = a.createOscillator(), g = a.createGain();
  o.type = type;
  o.frequency.setValueAtTime(freq, t);
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(vol, t + 0.01);
  g.gain.exponentialRampToValueAtTime(0.0001, t + Math.min(dur, 0.9));
  o.connect(g).connect(a.destination);
  o.start(t);
  o.stop(t + Math.min(dur, 0.9) + 0.05);
}

function schedule() {
  const a = ac();
  while (nextTime < a.currentTime + 0.4) {
    const [note, beats] = MELODY[idx];
    musicNote(N[note], nextTime, beats * BEAT, 0.035);                     // music-box melody
    musicNote(N[note] * 2, nextTime, beats * BEAT * 0.5, 0.008, "sine");   // sparkle overtone
    const bar = Math.floor(beatPos / 4);
    if (beatPos % 2 === 0) musicNote(N[BARS[bar % BARS.length]], nextTime, BEAT * 1.6, 0.025, "sine"); // soft bass
    nextTime += beats * BEAT;
    beatPos += beats;
    idx = (idx + 1) % MELODY.length;
    if (idx === 0) { beatPos = 0; nextTime += BEAT * 2; }                  // short breath between loops
  }
}

export const music = {
  start() {
    if (!musicOn || musicTimer) return;
    try { const a = ac(); nextTime = a.currentTime + 0.1; idx = 0; beatPos = 0; musicTimer = setInterval(schedule, 120); } catch (e) { /* no audio */ }
  },
  stop() { clearInterval(musicTimer); musicTimer = null; },
  isOn: () => musicOn,
  toggle() {
    musicOn = !musicOn;
    try { localStorage.setItem("sl-music", musicOn ? "1" : "0"); } catch (e) { /* ignore */ }
    musicOn ? music.start() : music.stop();
    return musicOn;
  },
};
// start the music on the first click anywhere (browsers block autoplay)
addEventListener("pointerdown", () => music.start(), { once: true });

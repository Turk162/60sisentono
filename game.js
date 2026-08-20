/* Gara di MotoGP per il compleanno di Rino.
   Canvas 2D, vista dall'alto, pista a scorrimento verticale. */
'use strict';

const canvas = document.getElementById('gioco');
const ctx = canvas.getContext('2d');

// ---- Stati ----
const S = { START: 0, COUNTDOWN: 1, RACE: 2, FINISH: 3 };
let stato = S.START;

// ---- Costanti di gioco (pixel CSS) ----
const VEL_CROCIERA = 520;                    // px/s di scorrimento pista
const DISTANZA_TOTALE = VEL_CROCIERA * 40;   // ~40 s a velocità piena
const R_PIZZA = 30;
const R_MOTO = 18;
const LARGH_MOTO = 36;

// ---- Stato di gara ----
let W = 0, H = 0, playerY = 0, hw = 0, amp = 0;
let dist = 0, vel = 0, fattoreVel = 1;
let playerX = 0, targetX = 0;
let shake = 0, tFinish = 0;
let pizze = [], particelle = [];
let pausa = false;

// ---- Canvas responsive con devicePixelRatio ----
function resize() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  W = window.innerWidth;
  H = window.innerHeight;
  canvas.width = Math.round(W * dpr);
  canvas.height = Math.round(H * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  playerY = H * 0.8;
  hw = Math.min(W * 0.32, 180);                    // semilarghezza pista
  amp = Math.max(20, (W / 2 - hw - 12) / 1.5);     // ampiezza curve
  // Avviso landscape (solo telefoni: in orizzontale l'altezza è poca)
  const landscape = W > H && H < 500;
  document.getElementById('ruota').classList.toggle('nascosto', !landscape);
  pausa = landscape;
}
window.addEventListener('resize', resize);
resize();

// Asse della pista in funzione della distanza percorsa
function centroPista(d) {
  return W / 2 + amp * (Math.sin(d * 0.0035) + 0.5 * Math.sin(d * 0.0016 + 1.3));
}

// ---- Sprite pre-renderizzati su canvas offscreen ----
function nuovoSprite(w, h, disegna) {
  const c = document.createElement('canvas');
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  c.width = w * dpr; c.height = h * dpr;
  const g = c.getContext('2d');
  g.scale(dpr, dpr);
  disegna(g);
  return c;
}

const spritePizza = nuovoSprite(64, 64, g => {
  g.translate(32, 32);
  g.fillStyle = '#d9a24b';                          // cornicione
  g.beginPath(); g.arc(0, 0, 30, 0, 7); g.fill();
  g.fillStyle = '#d84315';                          // pomodoro
  g.beginPath(); g.arc(0, 0, 24, 0, 7); g.fill();
  g.fillStyle = '#f5f0dc';                          // mozzarella
  for (const [x, y, r] of [[-9, -8, 8], [10, -4, 7], [-2, 9, 8], [8, 11, 6], [-13, 5, 6]]) {
    g.beginPath(); g.arc(x, y, r, 0, 7); g.fill();
  }
  g.fillStyle = '#2e7d32';                          // basilico
  for (const [x, y] of [[-5, -13], [13, 4], [-10, 12]]) {
    g.beginPath(); g.ellipse(x, y, 4, 2.5, 0.6, 0, 7); g.fill();
  }
});

const spriteMoto = nuovoSprite(LARGH_MOTO + 8, 76, g => {
  g.translate((LARGH_MOTO + 8) / 2, 38);
  g.fillStyle = '#111';                             // ruote
  g.beginPath(); g.roundRect(-5, -36, 10, 18, 5); g.fill();
  g.beginPath(); g.roundRect(-6, 16, 12, 20, 6); g.fill();
  g.fillStyle = '#c62828';                          // carena
  g.beginPath(); g.roundRect(-13, -22, 26, 42, 11); g.fill();
  g.fillStyle = '#8e1c1c';
  g.beginPath(); g.roundRect(-9, -20, 18, 12, 6); g.fill();  // cupolino
  g.fillStyle = '#222';                             // manubrio
  g.fillRect(-16, -12, 32, 5);
  g.fillStyle = '#f5f0e8';                          // casco
  g.beginPath(); g.arc(0, 2, 8, 0, 7); g.fill();
  g.fillStyle = '#c62828';
  g.beginPath(); g.arc(0, 2, 8, -0.6, 0.6); g.fill();
});

// ---- Audio sintetizzato (Web Audio, nessun file) ----
let audio = null;
function avviaAudio() {
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    const c = new AC();
    const osc = c.createOscillator();
    const gain = c.createGain();
    const filtro = c.createBiquadFilter();
    osc.type = 'sawtooth'; osc.frequency.value = 50;
    filtro.type = 'lowpass'; filtro.frequency.value = 400;
    gain.gain.value = 0;
    osc.connect(filtro).connect(gain).connect(c.destination);
    osc.start();
    audio = { c, osc, gain };
  } catch (e) { audio = null; }
}
function motore(attivo) {
  if (!audio) return;
  const v = vel * fattoreVel / VEL_CROCIERA;
  audio.osc.frequency.setTargetAtTime(45 + v * 70, audio.c.currentTime, 0.1);
  audio.gain.gain.setTargetAtTime(attivo ? 0.04 + v * 0.03 : 0, audio.c.currentTime, 0.15);
}
function suonoSplat() {
  if (!audio) return;
  const n = audio.c.createBufferSource();
  const buf = audio.c.createBuffer(1, 4410, 44100);
  const d = buf.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length);
  const g = audio.c.createGain(); g.gain.value = 0.25;
  n.buffer = buf; n.connect(g).connect(audio.c.destination); n.start();
}
function fanfara() {
  if (!audio) return;
  [523, 659, 784, 1047].forEach((f, i) => {
    const o = audio.c.createOscillator();
    const g = audio.c.createGain();
    o.type = 'square'; o.frequency.value = f;
    g.gain.value = 0;
    o.connect(g).connect(audio.c.destination);
    const t = audio.c.currentTime + i * 0.18;
    g.gain.setValueAtTime(0.08, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + (i === 3 ? 0.7 : 0.2));
    o.start(t); o.stop(t + 0.8);
  });
}
document.addEventListener('visibilitychange', () => {
  if (!audio) return;
  if (document.hidden) audio.c.suspend(); else audio.c.resume();
});

// ---- Input: Pointer Events (touch + mouse unificati) ----
let dito = false;
canvas.addEventListener('pointerdown', e => {
  dito = true; targetX = e.clientX;
  canvas.setPointerCapture(e.pointerId);
});
canvas.addEventListener('pointermove', e => { if (dito) targetX = e.clientX; });
canvas.addEventListener('pointerup', () => { dito = false; });
document.addEventListener('touchmove', e => e.preventDefault(), { passive: false });

// Fallback tastiera per test desktop
const tasti = {};
window.addEventListener('keydown', e => { tasti[e.key] = true; });
window.addEventListener('keyup', e => { tasti[e.key] = false; });

// ---- Preparazione gara ----
function generaPizze() {
  pizze = [];
  let d = 900;
  while (d < DISTANZA_TOTALE - 600) {
    const off = (Math.random() * 2 - 1) * (hw - R_PIZZA - 14);
    pizze.push({ d, off, colpita: false });
    let passo = 450 + Math.random() * 250;
    if (d > DISTANZA_TOTALE / 2) passo *= 0.85;   // densità crescente
    d += passo;
  }
}

function avviaGara() {
  dist = 0; vel = 0; fattoreVel = 1; shake = 0;
  playerX = targetX = centroPista(0);
  particelle = [];
  generaPizze();
  stato = S.COUNTDOWN;
  // Semaforo: 3 luci rosse, poi VIA!
  const sem = document.getElementById('semaforo');
  const luci = sem.querySelectorAll('.luce');
  const via = document.getElementById('via');
  sem.classList.remove('nascosto');
  via.classList.add('nascosto');
  luci.forEach(l => l.classList.remove('accesa'));
  luci.forEach((l, i) => setTimeout(() => l.classList.add('accesa'), 500 + i * 600));
  setTimeout(() => {
    luci.forEach(l => l.classList.remove('accesa'));
    via.classList.remove('nascosto');
    stato = S.RACE;
    setTimeout(() => sem.classList.add('nascosto'), 700);
  }, 500 + 3 * 600 + 500);
}

document.getElementById('btnParti').addEventListener('click', () => {
  document.getElementById('start').classList.add('nascosto');
  if (!audio) avviaAudio();
  avviaGara();
});

document.getElementById('btnRigioca').addEventListener('click', () => {
  const fin = document.getElementById('finish');
  fin.classList.add('nascosto');
  for (const id of ['auguri', 'premio', 'sottotitolo', 'btnRigioca'])
    document.getElementById(id).classList.remove('mostrato');
  avviaGara();
});

// ---- Traguardo e premio ----
function arrivo() {
  stato = S.FINISH;
  tFinish = 0;
  fanfara();
  // Coriandoli
  for (let i = 0; i < 70; i++) {
    particelle.push({
      x: Math.random() * W, y: -20 - Math.random() * H * 0.5,
      vx: (Math.random() - 0.5) * 60, vy: 80 + Math.random() * 120,
      rot: Math.random() * 6, vrot: (Math.random() - 0.5) * 8,
      col: ['#e53935', '#ffd54f', '#4caf50', '#42a5f5', '#f5f0e8'][i % 5],
      vita: 9, coriandolo: true
    });
  }
  const mostra = (id, ritardo) =>
    setTimeout(() => document.getElementById(id).classList.add('mostrato'), ritardo);
  setTimeout(() => document.getElementById('finish').classList.remove('nascosto'), 900);
  mostra('auguri', 1300);
  mostra('premio', 2200);
  mostra('sottotitolo', 3000);
  mostra('btnRigioca', 3400);
}

// ---- Aggiornamento ----
function aggiorna(dt) {
  if (stato === S.RACE) {
    vel = Math.min(VEL_CROCIERA, vel + VEL_CROCIERA * dt / 2.5);  // accelerazione automatica
    fattoreVel = Math.min(1, fattoreVel + dt * 0.3);              // recupero dopo penalità
  } else if (stato === S.FINISH) {
    vel = Math.max(0, vel - VEL_CROCIERA * dt / 1.2);             // decelerazione
    tFinish += dt;
  }
  dist += vel * fattoreVel * dt;
  if (stato === S.RACE && dist >= DISTANZA_TOTALE) arrivo();

  // Sterzata: la moto insegue il dito (o le frecce)
  if (stato === S.RACE) {
    if (tasti.ArrowLeft) targetX -= 300 * dt;
    if (tasti.ArrowRight) targetX += 300 * dt;
    targetX = Math.max(10, Math.min(W - 10, targetX));
    playerX += (targetX - playerX) * Math.min(1, dt * 8);

    // Bordi pista: rimbalzo + lieve rallentamento
    const c = centroPista(dist);
    const margine = hw - LARGH_MOTO / 2 - 4;
    if (playerX < c - margine) { playerX = c - margine; targetX = Math.max(targetX, playerX); fattoreVel = Math.min(fattoreVel, 0.75); }
    if (playerX > c + margine) { playerX = c + margine; targetX = Math.min(targetX, playerX); fattoreVel = Math.min(fattoreVel, 0.75); }

    // Collisione con le pizze (cerchio-cerchio, raggi generosi)
    for (const p of pizze) {
      if (p.colpita || Math.abs(p.d - dist) > 80) continue;
      const dx = playerX - (centroPista(p.d) + p.off);
      const dy = p.d - dist;
      const rr = (R_PIZZA + R_MOTO) * 0.8;
      if (dx * dx + dy * dy < rr * rr) {
        p.colpita = true;
        fattoreVel = 0.4;
        shake = 0.3;
        suonoSplat();
        for (let i = 0; i < 14; i++) {              // schizzi di pomodoro
          const a = Math.random() * 6.28, v = 60 + Math.random() * 160;
          particelle.push({
            x: playerX + dx * 0.3, y: playerY, vx: Math.cos(a) * v, vy: Math.sin(a) * v - 40,
            col: i % 3 ? '#d84315' : '#f5f0dc', vita: 0.7
          });
        }
      }
    }
  }

  shake = Math.max(0, shake - dt);
  for (const p of particelle) {
    p.vita -= dt;
    p.x += p.vx * dt; p.y += p.vy * dt;
    if (p.coriandolo) { p.rot += p.vrot * dt; }
    else p.vy += 500 * dt;
  }
  particelle = particelle.filter(p => p.vita > 0 && p.y < H + 30);
  motore(stato === S.RACE || (stato === S.FINISH && vel > 0));
}

// ---- Disegno ----
function disegna() {
  ctx.save();
  if (shake > 0) ctx.translate((Math.random() - 0.5) * shake * 40, (Math.random() - 0.5) * shake * 40);

  // Erba
  ctx.fillStyle = '#2f7d32';
  ctx.fillRect(-20, -20, W + 40, H + 40);

  // Pista a strisce orizzontali
  const passo = 6;
  for (let y = 0; y < H + passo; y += passo) {
    const d = dist + (playerY - y);
    const c = centroPista(d);
    ctx.fillStyle = '#3a3a3e';
    ctx.fillRect(c - hw, y, hw * 2, passo + 1);
    // Cordoli rosso/bianchi
    ctx.fillStyle = Math.floor(d / 40) % 2 ? '#e53935' : '#f5f0e8';
    ctx.fillRect(c - hw, y, 8, passo + 1);
    ctx.fillRect(c + hw - 8, y, 8, passo + 1);
    // Linea centrale tratteggiata
    if (Math.floor(d / 60) % 2) {
      ctx.fillStyle = 'rgba(245,240,232,0.5)';
      ctx.fillRect(c - 2, y, 4, passo + 1);
    }
    // Traguardo a scacchi
    const alTraguardo = DISTANZA_TOTALE - d;
    if (alTraguardo >= 0 && alTraguardo < 36) {
      const riga = Math.floor(alTraguardo / 12);
      for (let i = 0; i < 10; i++) {
        ctx.fillStyle = (i + riga) % 2 ? '#111' : '#f5f0e8';
        ctx.fillRect(c - hw + i * hw / 5, y, hw / 5, passo + 1);
      }
    }
  }

  // Pizze
  for (const p of pizze) {
    const y = playerY - (p.d - dist);
    if (y < -50 || y > H + 50) continue;
    const x = centroPista(p.d) + p.off;
    ctx.save();
    ctx.translate(x, y);
    if (p.colpita) { ctx.globalAlpha = 0.55; ctx.scale(1.25, 0.7); }
    ctx.drawImage(spritePizza, -32, -32, 64, 64);
    ctx.restore();
  }

  // Moto con inclinazione in sterzata
  if (stato !== S.START) {
    ctx.save();
    ctx.translate(playerX, playerY);
    ctx.rotate(Math.max(-0.35, Math.min(0.35, (targetX - playerX) * 0.006)));
    ctx.drawImage(spriteMoto, -(LARGH_MOTO + 8) / 2, -38, LARGH_MOTO + 8, 76);
    ctx.restore();
  }

  // Particelle (schizzi e coriandoli)
  for (const p of particelle) {
    ctx.save();
    ctx.translate(p.x, p.y);
    if (p.coriandolo) ctx.rotate(p.rot);
    ctx.fillStyle = p.col;
    ctx.globalAlpha = Math.min(1, p.vita * 2);
    if (p.coriandolo) ctx.fillRect(-4, -2, 8, 5); else ctx.fillRect(-3, -3, 6, 6);
    ctx.restore();
  }

  // HUD: barra di avanzamento + velocità scenica
  if (stato === S.RACE || stato === S.FINISH) {
    const pad = 16, yH = 54, wB = W - pad * 2 - 90;
    ctx.fillStyle = 'rgba(0,0,0,0.45)';
    ctx.beginPath(); ctx.roundRect(pad, yH, wB, 12, 6); ctx.fill();
    ctx.fillStyle = '#ffd54f';
    ctx.beginPath(); ctx.roundRect(pad, yH, Math.max(12, wB * Math.min(1, dist / DISTANZA_TOTALE)), 12, 6); ctx.fill();
    ctx.fillStyle = '#f5f0e8';
    ctx.font = 'bold 16px -apple-system, sans-serif';
    ctx.textAlign = 'right';
    ctx.fillText(Math.round(vel * fattoreVel * 0.6) + ' km/h', W - pad, yH + 12);
  }
  ctx.restore();
}

// ---- Loop principale ----
let tPrima = performance.now();
function loop(t) {
  const dt = Math.min(0.05, (t - tPrima) / 1000);  // clamp: identico a 60/120 Hz
  tPrima = t;
  if (!pausa) { aggiorna(dt); disegna(); }
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);

/* Gara di moto per il compleanno di Rino.
   Canvas 2D, vista dall'alto, pista a scorrimento verticale.
   Ostacoli satirici da schivare, pizze come power-up, 3 vite. */
'use strict';

const canvas = document.getElementById('gioco');
const ctx = canvas.getContext('2d');

// ---- Stati ----
const S = { START: 0, COUNTDOWN: 1, RACE: 2, FINISH: 3, GAMEOVER: 4 };
let stato = S.START;

// ---- Costanti di gioco (pixel CSS) ----
const VEL_CROCIERA = 520;                    // px/s di scorrimento pista
const DISTANZA_TOTALE = VEL_CROCIERA * 40;   // ~40 s a velocità piena
const R_PIZZA = 30;
const R_MOTO = 18;
const LARGH_MOTO = 36;
const VITE_MAX = 3;

// ---- Stato di gara ----
let W = 0, H = 0, playerY = 0, hw = 0, amp = 0;
let dist = 0, vel = 0, fattoreVel = 1;
let playerX = 0, targetX = 0;
let shake = 0, tFinish = 0;
let vite = VITE_MAX, scudoT = 0, turboT = 0, invulnT = 0;
let oggetti = [], particelle = [];
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

// Omino generico: gambe, braccia, testa; il busto lo disegna `busto(g)`
function spriteOmino(w, h, scala, mezzoTorso, busto, extra) {
  return nuovoSprite(Math.round(w * scala), Math.round(h * scala), g => {
    g.scale(scala, scala);
    g.translate(w / 2, h - 72);
    g.fillStyle = '#2b3a55';                        // gambe
    g.fillRect(-10, 44, 8, 24); g.fillRect(2, 44, 8, 24);
    busto(g);                                       // busto in -mezzoTorso..mezzoTorso, 16..46
    g.fillStyle = '#e8b88a';                        // braccia
    g.fillRect(-mezzoTorso - 6, 18, 6, 22); g.fillRect(mezzoTorso, 18, 6, 22);
    g.beginPath(); g.arc(0, 6, 9, 0, 7); g.fill(); // testa
    if (extra) extra(g);
  });
}

const SPRITE_OSTACOLI = [
  // 0: tifoso juventino (maglia a strisce bianconere)
  spriteOmino(64, 80, 1.25, 14, g => {
    g.fillStyle = '#f5f0e8';
    g.fillRect(-14, 16, 28, 30);
    g.fillStyle = '#111';
    for (let x = -14; x < 14; x += 8) g.fillRect(x, 16, 4, 30);
  }),
  // 1: Duomo di Milano con la Madonnina e la scritta
  nuovoSprite(140, 104, g => {
    g.translate(70, 0);
    g.fillStyle = '#ded8cc';
    g.beginPath();                                  // facciata a capanna
    g.moveTo(-36, 72); g.lineTo(-36, 40); g.lineTo(0, 16); g.lineTo(36, 40); g.lineTo(36, 72);
    g.closePath(); g.fill();
    g.fillStyle = '#cfc8ba';                        // guglie
    for (const [x, hg] of [[-30, 26], [-16, 34], [16, 34], [30, 26]]) {
      g.beginPath(); g.moveTo(x - 3, 72); g.lineTo(x, 72 - hg - 14); g.lineTo(x + 3, 72); g.fill();
    }
    g.beginPath(); g.moveTo(-4, 40); g.lineTo(0, 6); g.lineTo(4, 40); g.fill(); // guglia maggiore
    g.fillStyle = '#f2c53d';                        // Madonnina
    g.beginPath(); g.arc(0, 5, 4, 0, 7); g.fill();
    g.fillStyle = '#8a8478';                        // portone
    g.beginPath(); g.arc(0, 58, 7, 3.14, 0); g.fill(); g.fillRect(-7, 58, 14, 14);
    g.fillStyle = '#fff';                           // targa con la scritta
    g.strokeStyle = '#1a3f8f'; g.lineWidth = 2;
    g.beginPath(); g.roundRect(-66, 78, 132, 22, 4); g.fill(); g.stroke();
    g.fillStyle = '#1a3f8f';
    g.font = 'italic bold 13px sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText('O mia bela madunina', 0, 90);
  }),
  // 2: bandiera della Lega (logo caricato da lega_logo.jpg)
  (() => {
    const s = nuovoSprite(72, 88, g => {
      g.translate(8, 0);
      g.fillStyle = '#7a7a7a';                      // asta
      g.fillRect(-2, 4, 4, 80);
      g.fillStyle = '#fff';                         // drappo bianco
      g.strokeStyle = '#1a3f8f'; g.lineWidth = 2;
      g.beginPath(); g.roundRect(2, 6, 56, 42, 3); g.fill(); g.stroke();
    });
    const logo = new Image();
    logo.onload = () => {
      const g = s.getContext('2d');
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.drawImage(logo, 20, 8, 38, 38);             // centrato nel drappo
    };
    logo.src = 'lega_logo.jpg';
    return s;
  })(),
  // 3: omino con la maglia verde e la scritta SALVINI
  spriteOmino(70, 80, 1.3, 22, g => {
    g.fillStyle = '#1b8a3a';                        // maglia verde
    g.beginPath(); g.roundRect(-22, 16, 44, 30, 4); g.fill();
    g.fillStyle = '#fff';
    g.font = 'bold 10px sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText('SALVINI', 0, 31);
  }),
  // 4: omino Vannacci con la maglia arcobaleno
  spriteOmino(82, 80, 1.3, 27, g => {
    const colori = ['#e53935', '#ff9800', '#ffd54f', '#4caf50', '#42a5f5', '#8e5bb5'];
    colori.forEach((c, i) => {                      // maglia arcobaleno
      g.fillStyle = c;
      g.fillRect(-27, 16 + i * 5, 54, 5);
    });
    g.strokeStyle = '#fff'; g.lineWidth = 3;
    g.font = 'bold 10px sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.strokeText('VANNACCI', 0, 31);
    g.fillStyle = '#111';
    g.fillText('VANNACCI', 0, 31);
  }, g => {
    g.fillStyle = '#46552e';                        // elmetto
    g.beginPath(); g.arc(0, 3, 10, 3.14, 0); g.fill();
  }),
  // 5: cartello stradale FI-PI-LI
  nuovoSprite(84, 92, g => {
    g.translate(42, 0);
    g.fillStyle = '#7a7a7a';                        // palo
    g.fillRect(-3, 36, 6, 52);
    g.fillStyle = '#1565c0';                        // pannello blu
    g.strokeStyle = '#f5f0e8'; g.lineWidth = 3;
    g.beginPath(); g.roundRect(-36, 2, 72, 36, 4); g.fill(); g.stroke();
    g.fillStyle = '#f5f0e8';
    g.font = 'bold 16px sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText('FI-PI-LI', 0, 21);
  }),
  // 6: Frecciarossa Trenitalia
  nuovoSprite(150, 48, g => {
    g.fillStyle = '#d9d9de';                        // cassa
    g.beginPath(); g.roundRect(2, 8, 132, 30, 6); g.fill();
    g.fillStyle = '#8a1c1c';                        // muso
    g.beginPath();
    g.moveTo(134, 8); g.quadraticCurveTo(150, 20, 148, 38); g.lineTo(134, 38);
    g.closePath(); g.fill();
    g.fillStyle = '#c62828';                        // fascia rossa
    g.fillRect(2, 32, 132, 6);
    g.fillStyle = '#33373d';                        // finestrini
    for (let x = 10; x < 126; x += 16) g.fillRect(x, 11, 10, 6);
    g.fillStyle = '#c62828';
    g.font = 'italic bold 12px sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText('TRENITALIA', 67, 26);
  })
];

// Raggio di collisione per tipo di ostacolo
const RAGGI_OSTACOLI = [26, 30, 26, 28, 28, 28, 36];

// Power-up pizza: tipo -> simbolo del distintivo
const PIZZE = { turbo: '⚡', vita: '❤️', scudo: '🛡️' };

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
function suonoBeep(freq, dur) {
  if (!audio) return;
  const o = audio.c.createOscillator();
  const g = audio.c.createGain();
  o.type = 'square'; o.frequency.value = freq;
  o.connect(g).connect(audio.c.destination);
  const t = audio.c.currentTime;
  g.gain.setValueAtTime(0.12, t);
  g.gain.exponentialRampToValueAtTime(0.001, t + dur);
  o.start(t); o.stop(t + dur + 0.05);
}
function suonoPickup() {
  if (!audio) return;
  [660, 990].forEach((f, i) => {
    const o = audio.c.createOscillator();
    const g = audio.c.createGain();
    o.type = 'sine'; o.frequency.value = f;
    o.connect(g).connect(audio.c.destination);
    const t = audio.c.currentTime + i * 0.09;
    g.gain.setValueAtTime(0.12, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + 0.15);
    o.start(t); o.stop(t + 0.2);
  });
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
function generaOggetti() {
  oggetti = [];
  // Ostacoli
  let d = 900;
  while (d < DISTANZA_TOTALE - 600) {
    const tipo = Math.floor(Math.random() * SPRITE_OSTACOLI.length);
    const r = RAGGI_OSTACOLI[tipo];
    const off = (Math.random() * 2 - 1) * (hw - r - 18);
    oggetti.push({ d, off, tipo, r, colpito: false });
    let passo = 450 + Math.random() * 250;
    if (d > DISTANZA_TOTALE / 2) passo *= 0.85;   // densità crescente
    d += passo;
  }
  // Pizze power-up, lontane dagli ostacoli
  const tipi = ['turbo', 'scudo', 'vita', 'turbo', 'scudo'];
  let i = 0;
  for (let dp = 1600; dp < DISTANZA_TOTALE - 800; dp += 2600 + Math.random() * 900) {
    while (oggetti.some(o => !o.pizza && Math.abs(o.d - dp) < 200)) dp += 120;
    const off = (Math.random() * 2 - 1) * (hw - R_PIZZA - 14);
    oggetti.push({ d: dp, off, pizza: tipi[i++ % tipi.length], r: R_PIZZA, colpito: false });
  }
}

function avviaGara() {
  dist = 0; vel = 0; fattoreVel = 1; shake = 0;
  vite = VITE_MAX; scudoT = 0; turboT = 0; invulnT = 0;
  playerX = targetX = centroPista(0);
  particelle = [];
  generaOggetti();
  stato = S.COUNTDOWN;
  // Semaforo: 3 luci rosse, poi VIA!
  const sem = document.getElementById('semaforo');
  const luci = sem.querySelectorAll('.luce');
  const via = document.getElementById('via');
  sem.classList.remove('nascosto');
  via.classList.add('nascosto');
  luci.forEach(l => l.classList.remove('accesa'));
  luci.forEach((l, i) => setTimeout(() => { l.classList.add('accesa'); suonoBeep(440, 0.18); }, 500 + i * 600));
  setTimeout(() => {
    luci.forEach(l => l.classList.remove('accesa'));
    via.classList.remove('nascosto');
    suonoBeep(880, 0.5);
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

document.getElementById('btnRiprova').addEventListener('click', () => {
  document.getElementById('gameover').classList.add('nascosto');
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

function schizzi(x, y, colori) {
  for (let i = 0; i < 14; i++) {
    const a = Math.random() * 6.28, v = 60 + Math.random() * 160;
    particelle.push({
      x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v - 40,
      col: colori[i % colori.length], vita: 0.7
    });
  }
}

// ---- Aggiornamento ----
function aggiorna(dt) {
  if (stato === S.RACE) {
    vel = Math.min(VEL_CROCIERA, vel + VEL_CROCIERA * dt / 2.5);  // accelerazione automatica
    fattoreVel = Math.min(1, fattoreVel + dt * 0.3);              // recupero dopo penalità
  } else if (stato === S.FINISH || stato === S.GAMEOVER) {
    vel = Math.max(0, vel - VEL_CROCIERA * dt / 1.2);             // decelerazione
    tFinish += dt;
  }
  scudoT = Math.max(0, scudoT - dt);
  turboT = Math.max(0, turboT - dt);
  invulnT = Math.max(0, invulnT - dt);
  const turbo = turboT > 0 ? 1.45 : 1;
  dist += vel * fattoreVel * turbo * dt;
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

    // Collisioni (cerchio-cerchio)
    for (const o of oggetti) {
      if (o.colpito || Math.abs(o.d - dist) > 90) continue;
      const dx = playerX - (centroPista(o.d) + o.off);
      const dy = o.d - dist;
      const rr = (o.r + R_MOTO) * (o.pizza ? 0.95 : 0.8);
      if (dx * dx + dy * dy >= rr * rr) continue;
      o.colpito = true;
      if (o.pizza) {                                // power-up!
        suonoPickup();
        schizzi(playerX, playerY, ['#ffd54f', '#f5f0dc']);
        if (o.pizza === 'turbo') turboT = 4;
        else if (o.pizza === 'scudo') scudoT = 3;
        else if (o.pizza === 'vita') vite = Math.min(VITE_MAX, vite + 1);
      } else if (scudoT > 0) {                      // lo scudo spazza via l'ostacolo
        suonoSplat();
        schizzi(playerX + dx * 0.3, playerY, ['#42a5f5', '#f5f0e8']);
      } else if (invulnT <= 0) {                    // botta: -1 vita
        suonoSplat();
        schizzi(playerX + dx * 0.3, playerY, ['#d84315', '#8a8478']);
        fattoreVel = 0.4;
        shake = 0.3;
        invulnT = 1.5;
        vite--;
        if (vite <= 0) {
          stato = S.GAMEOVER;
          tFinish = 0;
          setTimeout(() => document.getElementById('gameover').classList.remove('nascosto'), 900);
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
  motore(stato === S.RACE || ((stato === S.FINISH || stato === S.GAMEOVER) && vel > 0));
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

  // Ostacoli e pizze
  for (const o of oggetti) {
    const y = playerY - (o.d - dist);
    if (y < -70 || y > H + 70) continue;
    const x = centroPista(o.d) + o.off;
    ctx.save();
    ctx.translate(x, y);
    if (o.colpito) { ctx.globalAlpha = 0.45; ctx.rotate(0.5); ctx.scale(1.1, 0.7); }
    if (o.pizza) {
      ctx.drawImage(spritePizza, -32, -32, 64, 64);
      if (!o.colpito) {                             // distintivo del power-up
        ctx.fillStyle = '#f5f0e8';
        ctx.beginPath(); ctx.arc(20, -20, 11, 0, 7); ctx.fill();
        ctx.font = '13px sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText(PIZZE[o.pizza], 20, -19);
      }
    } else {
      const s = SPRITE_OSTACOLI[o.tipo];
      const w = s.width / Math.min(window.devicePixelRatio || 1, 2);
      const h = s.height / Math.min(window.devicePixelRatio || 1, 2);
      ctx.drawImage(s, -w / 2, -h / 2, w, h);
    }
    ctx.restore();
  }

  // Moto con inclinazione in sterzata (lampeggia se invulnerabile)
  if (stato !== S.START) {
    ctx.save();
    ctx.translate(playerX, playerY);
    if (invulnT > 0 && Math.floor(invulnT * 10) % 2) ctx.globalAlpha = 0.35;
    ctx.rotate(Math.max(-0.35, Math.min(0.35, (targetX - playerX) * 0.006)));
    if (turboT > 0) {                               // fiammate del turbo
      ctx.fillStyle = Math.floor(performance.now() / 60) % 2 ? '#ff9800' : '#ffd54f';
      ctx.beginPath(); ctx.moveTo(-7, 38); ctx.lineTo(0, 38 + 16 + Math.random() * 8); ctx.lineTo(7, 38); ctx.fill();
    }
    ctx.drawImage(spriteMoto, -(LARGH_MOTO + 8) / 2, -38, LARGH_MOTO + 8, 76);
    ctx.restore();
    if (scudoT > 0) {                               // aura dello scudo
      ctx.strokeStyle = `rgba(66,165,245,${0.5 + 0.3 * Math.sin(performance.now() / 120)})`;
      ctx.lineWidth = 3;
      ctx.beginPath(); ctx.arc(playerX, playerY, 42, 0, 7); ctx.stroke();
    }
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

  // HUD: barra di avanzamento, velocità, vite e bonus attivi
  if (stato === S.RACE || stato === S.FINISH || stato === S.GAMEOVER) {
    const pad = 16, yH = 54, wB = W - pad * 2 - 110;
    ctx.fillStyle = 'rgba(0,0,0,0.45)';
    ctx.beginPath(); ctx.roundRect(pad, yH, wB, 12, 6); ctx.fill();
    ctx.fillStyle = '#ffd54f';
    ctx.beginPath(); ctx.roundRect(pad, yH, Math.max(12, wB * Math.min(1, dist / DISTANZA_TOTALE)), 12, 6); ctx.fill();
    ctx.fillStyle = '#f5f0e8';
    ctx.font = 'bold 16px -apple-system, sans-serif';
    ctx.textAlign = 'right'; ctx.textBaseline = 'alphabetic';
    ctx.fillText(Math.round(vel * fattoreVel * (turboT > 0 ? 1.45 : 1) * 0.6) + ' km/h', W - pad, yH + 12);
    ctx.textAlign = 'left';
    ctx.font = '18px sans-serif';
    let cuori = '❤️'.repeat(vite) + '🖤'.repeat(VITE_MAX - vite);
    if (scudoT > 0) cuori += '  🛡️';
    if (turboT > 0) cuori += '  ⚡';
    ctx.fillText(cuori, pad, yH + 38);
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

// Sonde di sola lettura per i test automatici
window.__debug = {
  get stato() { return stato; }, get vite() { return vite; }, get dist() { return dist; },
  get playerX() { return playerX; }, get oggetti() { return oggetti; },
  get scudoT() { return scudoT; }, get turboT() { return turboT; },
  centroPista
};

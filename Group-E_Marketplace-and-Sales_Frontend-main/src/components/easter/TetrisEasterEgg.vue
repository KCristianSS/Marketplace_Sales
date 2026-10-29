<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, type Component } from 'vue';
import {
  Archive, ArrowDown, ArrowLeft, ArrowRight, Bomb, ChevronsDown, Eye, Flame, Pause, Play,
  RotateCcw, RotateCw, Shield, Snail, Sparkles, Trophy, Volume2, VolumeX, X, Zap,
} from 'lucide-vue-next';
import {
  activateOverdrive, BLITZ_DURATION, type GameMode, BOARD_HEIGHT, BOARD_WIDTH, FEVER_DURATION_MS, HIDDEN_ROWS, LINES_PER_LEVEL, UPGRADES,
  chooseUpgrade, createGame, drainEvents, ghostY, hardDrop, holdPiece, isFever, move, pieceCells,
  rotate, scoreMultiplier, shapeOf, tick, useBomb, useLaser,
  type CellType, type GameState, type UpgradeId,
} from '@/game/tetris';

type Phase = 'closed' | 'intro' | 'playing' | 'paused' | 'over';
type Tone = 'gold' | 'teal' | 'coral' | 'violet' | 'rainbow' | 'white';
interface Colors { base: string; light: string; dark: string }
interface Popup { id: number; text: string; sub?: string; tone: Tone; x: number; y: number; big: boolean }
interface Particle { x: number; y: number; vx: number; vy: number; life: number; max: number; color: string; size: number; gravity: number }

const SECRET = 'tetris';
const CELL = 32;
const VISIBLE_ROWS = BOARD_HEIGHT - HIDDEN_ROWS;
const BOARD_PX_W = BOARD_WIDTH * CELL;
const BOARD_PX_H = VISIBLE_ROWS * CELL;
const DAS_MS = 140;
const ARR_MS = 35;
const BEST_KEY = 'maxi-tetris-best';
const MUTE_KEY = 'maxi-tetris-muted';

const PALETTE: Record<CellType, Colors> = {
  I: { base: '#22d3ee', light: '#a5f3fc', dark: '#0e7490' },
  O: { base: '#facc15', light: '#fef08a', dark: '#a16207' },
  T: { base: '#c084fc', light: '#e9d5ff', dark: '#7e22ce' },
  S: { base: '#4ade80', light: '#bbf7d0', dark: '#15803d' },
  Z: { base: '#fb7185', light: '#fecdd3', dark: '#be123c' },
  J: { base: '#60a5fa', light: '#bfdbfe', dark: '#1d4ed8' },
  L: { base: '#fb923c', light: '#fed7aa', dark: '#c2410c' },
  B: { base: '#f43f5e', light: '#ffe4e6', dark: '#881337' },
};
const SPARK_COLORS = ['#facc15', '#fde68a', '#22d3ee', '#c084fc', '#4ade80', '#fb7185', '#ffffff'];

const UPGRADE_ICONS: Record<UpgradeId, Component> = {
  slowMo: Snail, multiplier: Sparkles, vision: Eye, bomb: Bomb, laser: Zap, shield: Shield,
};
const UPGRADE_COLORS: Record<UpgradeId, string> = {
  slowMo: '#4ade80', multiplier: '#facc15', vision: '#c084fc', bomb: '#fb7185', laser: '#22d3ee', shield: '#60a5fa',
};

const mode = ref<GameMode>('arcade');
const modes = [
  { id: 'arcade' as const, name: 'Arcade', copy: 'Sin límite. Evoluciona tu partida.' },
  { id: 'sprint' as const, name: 'Sprint 40', copy: '40 líneas. Contra el reloj.' },
  { id: 'blitz' as const, name: 'Blitz 2:00', copy: 'Dos minutos. Máximo puntaje.' },
];
const depth = ref(readStorage('maxi-tetris-depth') !== '0');
const calm = ref(readStorage('maxi-tetris-calm') === '1');
const music = ref(readStorage('maxi-tetris-music') === '1');
const theme = ref(readStorage('maxi-tetris-theme') || 'nebula');
const themes = [
  { id: 'nebula', name: 'Nebulosa', hue: 272, color: '#a78bfa' },
  { id: 'aurora', name: 'Aurora', hue: 172, color: '#2dd4bf' },
  { id: 'sunset', name: 'Atardecer', hue: 22, color: '#fb923c' },
];
function setTheme(id: string): void {
  theme.value = id;
  writeStorage('maxi-tetris-theme', id);
}
function toggleSetting(setting: 'depth' | 'calm' | 'music'): void {
  const value = { depth, calm, music }[setting];
  value.value = !value.value;
  writeStorage(`maxi-tetris-${setting}`, value.value ? '1' : '0');
  if (setting === 'music') ensureAudio();
}
const heroPieces = ['T', 'I', 'L', 'S', 'O'] as const;
const achievement = ref('');
let achievementLife = 0;
let musicStep = -1;
let milestones = new Set<string>();
const ranks = [
  { name: 'Cadete', score: 0 }, { name: 'Piloto', score: 2500 },
  { name: 'As', score: 7500 }, { name: 'Élite', score: 15000 },
  { name: 'Leyenda', score: 30000 },
];
const phase = ref<Phase>('closed');
const isOpen = computed(() => phase.value !== 'closed');
const muted = ref(readStorage(MUTE_KEY) === '1');
const boardCanvas = ref<HTMLCanvasElement | null>(null);
const holdCanvas = ref<HTMLCanvasElement | null>(null);
const nextCanvas = ref<HTMLCanvasElement | null>(null);
const boardShell = ref<HTMLElement | null>(null);
const popups = ref<Popup[]>([]);
const scorePulse = ref(0);

const hud = reactive({
  energy: 0, time: 0, won: false, missionLines: 0, missionTarget: 4, missions: 0,
  score: 0,
  displayScore: 0,
  level: 1,
  lines: 0,
  combo: -1,
  multiplier: 1,
  fever: 0,
  previews: 3,
  slowMo: 0,
  bombs: 0,
  lasers: 0,
  shields: 0,
  choices: null as UpgradeId[] | null,
  best: Number(readStorage(BEST_KEY)) || 0,
  newBest: false,
  maxCombo: 0,
  tetrises: 0,
  danger: false,
});

const clockText = computed(() => {
  const seconds = Math.floor((mode.value === 'blitz' ? Math.max(0, BLITZ_DURATION - hud.time) : hud.time) / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
});
const bestKey = () => mode.value === 'arcade' ? BEST_KEY : `${BEST_KEY}-${mode.value}`;
const rank = computed(() => [...ranks].reverse().find(item => hud.score >= item.score)!);
const nextRank = computed(() => ranks.find(item => item.score > hud.score));
const rankProgress = computed(() => nextRank.value ? (hud.score - rank.value.score) / (nextRank.value.score - rank.value.score) : 1);
const levelHue = computed(() => ((themes.find(item => item.id === theme.value)?.hue ?? 272) + (hud.level - 1) * 12) % 360);
const levelProgress = computed(() => (hud.lines % LINES_PER_LEVEL) / LINES_PER_LEVEL);
const formattedScore = computed(() => Math.round(hud.displayScore).toLocaleString('es-BO'));

let game: GameState | null = null;
let secretBuffer = '';
let rafId = 0;
let lastFrame = 0;
let dpr = 1;
let popupId = 0;
let shake = 0;
let particles: Particle[] = [];
let rowFlashes: Array<{ y: number; life: number; max: number; color: string }> = [];
let cellFlashes: Array<{ x: number; y: number; life: number }> = [];
let trails: Array<{ x: number; top: number; bottom: number; life: number; color: string }> = [];
let shockwaves: Array<{ x: number; y: number; life: number; max: number; color: string; radius: number }> = [];
const held = { left: false, right: false, down: false };
let dasDirection = 0;
let dasTimer = 0;
let arrTimer = 0;
let previousBodyOverflow = '';
let audioContext: AudioContext | null = null;
const reducedMotion = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage can be unavailable in private mode; the game still works without persistence.
  }
}

// ---------- Audio ----------
function ensureAudio(): void {
  if (!audioContext) {
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (Ctor) audioContext = new Ctor();
  }
  if (audioContext?.state === 'suspended') void audioContext.resume();
}

function tone(frequency: number, duration: number, options: { type?: OscillatorType; volume?: number; slide?: number; delay?: number } = {}): void {
  if (muted.value || !audioContext) return;
  const start = audioContext.currentTime + (options.delay ?? 0);
  const oscillator = audioContext.createOscillator();
  const gain = audioContext.createGain();
  oscillator.type = options.type ?? 'square';
  oscillator.frequency.setValueAtTime(frequency, start);
  if (options.slide) oscillator.frequency.exponentialRampToValueAtTime(options.slide, start + duration);
  gain.gain.setValueAtTime(options.volume ?? 0.04, start);
  gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
  oscillator.connect(gain).connect(audioContext.destination);
  oscillator.start(start);
  oscillator.stop(start + duration + 0.02);
}

const note = (semitones: number, base = 523.25) => base * Math.pow(2, semitones / 12);

const sfx = {
  move: () => tone(240, 0.03, { type: 'triangle', volume: 0.015 }),
  rotate: () => tone(480, 0.04, { type: 'triangle', volume: 0.022 }),
  hold: () => tone(330, 0.07, { type: 'sine', volume: 0.04, slide: 500 }),
  lock: () => tone(130, 0.06, { type: 'square', volume: 0.025 }),
  drop: () => tone(320, 0.12, { type: 'sawtooth', volume: 0.035, slide: 70 }),
  clear: (count: number, combo: number) => {
    const shift = Math.min(12, Math.max(0, combo) * 2);
    [0, 4, 7, 12, 16].slice(0, count + 1).forEach((step, index) =>
      tone(note(step + shift), 0.14, { type: 'square', volume: 0.035, delay: index * 0.055 }));
    if (count >= 4) [19, 24, 28].forEach((step, index) => tone(note(step + shift), 0.2, { type: 'triangle', volume: 0.04, delay: 0.3 + index * 0.07 }));
  },
  levelUp: () => [0, 4, 7, 12, 7, 12, 16, 24].forEach((step, index) => tone(note(step), 0.12, { type: 'square', volume: 0.035, delay: index * 0.07 })),
  explode: () => {
    tone(180, 0.45, { type: 'sawtooth', volume: 0.06, slide: 35 });
    tone(90, 0.5, { type: 'square', volume: 0.04, slide: 30, delay: 0.03 });
  },
  laser: () => tone(1400, 0.3, { type: 'square', volume: 0.04, slide: 160 }),
  fever: () => [0, 3, 7, 10, 12, 15, 19, 24].forEach((step, index) => tone(note(step, 659.25), 0.08, { type: 'sawtooth', volume: 0.03, delay: index * 0.04 })),
  shield: () => tone(260, 0.4, { type: 'sine', volume: 0.06, slide: 900 }),
  pick: () => [0, 7, 12].forEach((step, index) => tone(note(step, 784), 0.1, { type: 'triangle', volume: 0.04, delay: index * 0.05 })),
  gameOver: () => [12, 7, 3, 0, -5].forEach((step, index) => tone(note(step, 392), 0.22, { type: 'triangle', volume: 0.045, delay: index * 0.16 })),
};

function toggleMute(): void {
  muted.value = !muted.value;
  writeStorage(MUTE_KEY, muted.value ? '1' : '0');
}

// ---------- Lifecycle of the overlay ----------
async function openGame(): Promise<void> {
  if (phase.value !== 'closed') return;
  previousBodyOverflow = document.body.style.overflow;
  document.body.style.overflow = 'hidden';
  game = createGame(Math.random, mode.value);
  resetEffects();
  syncHud();
  hud.displayScore = 0;
  phase.value = 'intro';
  await nextTick();
  setupCanvases();
  lastFrame = performance.now();
  rafId = requestAnimationFrame(frame);
}

function closeGame(): void {
  cancelAnimationFrame(rafId);
  rafId = 0;
  phase.value = 'closed';
  game = null;
  popups.value = [];
  document.body.style.overflow = previousBodyOverflow;
  releaseInputs();
}

function startGame(): void {
  ensureAudio();
  releaseInputs();
  hud.best = Number(readStorage(bestKey())) || 0;
  game = createGame(Math.random, mode.value);
  resetEffects();
  milestones = new Set();
  musicStep = -1;
  hud.maxCombo = 0;
  hud.tetrises = 0;
  hud.newBest = false;
  hud.displayScore = 0;
  syncHud();
  phase.value = 'playing';
  popup('¡A JUGAR!', { tone: 'teal', y: 40, big: true });
}

function returnToLobby(): void {
  releaseInputs();
  resetEffects();
  phase.value = 'intro';
}

function celebrate(id: string, label: string): void {
  if (milestones.has(id)) return;
  milestones.add(id);
  achievement.value = label;
  achievementLife = 3200;
  sfx.pick();
}

// A short original pentatonic sequence, scheduled only while the game advances.
function soundtrack(): void {
  if (!game || !music.value || muted.value || game.upgradeChoices) return;
  const step = Math.floor(game.time / 180);
  if (step === musicStep) return;
  musicStep = step;
  const melody = [0, 7, 12, 14, 7, 12, 19, 14, 3, 10, 15, 19, 10, 15, 22, 19];
  tone(note(melody[step % melody.length], 220), 0.16, { type: 'sine', volume: 0.014 });
  if (step % 4 === 0) tone(step % 16 < 8 ? 55 : 65.41, 0.24, { type: 'triangle', volume: 0.025 });
  if (isFever(game) && step % 2 === 0) tone(110, 0.08, { type: 'sine', volume: 0.025, slide: 40 });
}

function togglePause(): void {
  if (phase.value === 'playing') {
    phase.value = 'paused';
    releaseInputs();
  } else if (phase.value === 'paused') {
    phase.value = 'playing';
  }
}

function endGame(): void {
  phase.value = 'over';
  releaseInputs();
  if (game?.won) sfx.levelUp();
  else sfx.gameOver();
  if (game && game.score > hud.best) {
    hud.best = game.score;
    hud.newBest = true;
    writeStorage(bestKey(), String(game.score));
  }
}

function pickUpgrade(id: UpgradeId): void {
  if (!game || !chooseUpgrade(game, id)) return;
  sfx.pick();
  popup(UPGRADES[id].name.toUpperCase(), { tone: 'gold', y: 45, big: true });
  burst(BOARD_PX_W / 2, BOARD_PX_H / 2, 60, SPARK_COLORS, 5);
  syncHud();
}

function resetEffects(): void {
  achievement.value = '';
  achievementLife = 0;
  particles = [];
  rowFlashes = [];
  cellFlashes = [];
  trails = [];
  shockwaves = [];
  shake = 0;
  popups.value = [];
}

function releaseInputs(): void {
  held.left = false;
  held.right = false;
  held.down = false;
  dasDirection = 0;
}

// ---------- Input ----------
function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName);
}

function detectSecret(event: KeyboardEvent): void {
  if (event.ctrlKey || event.metaKey || event.altKey || isEditableTarget(event.target)) {
    secretBuffer = '';
    return;
  }
  if (event.key.length !== 1) return;
  secretBuffer = (secretBuffer + event.key.toLowerCase()).slice(-SECRET.length);
  if (secretBuffer === SECRET) {
    secretBuffer = '';
    ensureAudio();
    void openGame();
  }
}

function startShift(direction: number): void {
  dasDirection = direction;
  dasTimer = 0;
  arrTimer = 0;
  if (game && move(game, direction)) sfx.move();
}

function releaseShift(direction: number): void {
  if (dasDirection !== direction) return;
  const fallback = direction === -1 ? (held.right ? 1 : 0) : (held.left ? -1 : 0);
  dasDirection = 0;
  if (fallback) startShift(fallback);
}

function doRotate(direction: 1 | -1): void {
  if (game && rotate(game, direction)) sfx.rotate();
}

function doHardDrop(): void {
  if (game) hardDrop(game);
}

function doHold(): void {
  if (game && holdPiece(game)) sfx.hold();
}

function doBomb(): void {
  if (!game) return;
  if (useBomb(game)) {
    tone(880, 0.12, { type: 'square', volume: 0.04, slide: 440 });
    popup('BOMBA ARMADA', { tone: 'coral', y: 20 });
  }
}

function doOverdrive(): void {
  if (game && activateOverdrive(game)) syncHud();
}

function doLaser(): void {
  if (game) useLaser(game);
}

function handleGameKey(key: string, repeat: boolean): boolean {
  if (key === 'Tab') return false;
  if (key === 'm') {
    toggleMute();
    return true;
  }
  if (phase.value === 'intro' || phase.value === 'over') {
    if (key === 'Enter' || key === ' ' || key === 'r') startGame();
    else if (key === 'Escape') closeGame();
    return true;
  }
  if (phase.value === 'paused') {
    if (key === 'p' || key === 'Enter') togglePause();
    else if (key === 'Escape') closeGame();
    return true;
  }
  if (!game) return false;
  if (game.upgradeChoices) {
    const index = ['1', '2', '3'].indexOf(key);
    if (index >= 0 && game.upgradeChoices[index]) pickUpgrade(game.upgradeChoices[index]);
    return true;
  }
  switch (key) {
    case 'ArrowLeft':
    case 'a':
      if (!repeat) {
        held.left = true;
        startShift(-1);
      }
      return true;
    case 'ArrowRight':
    case 'd':
      if (!repeat) {
        held.right = true;
        startShift(1);
      }
      return true;
    case 'ArrowDown':
    case 's':
      held.down = true;
      return true;
    case 'ArrowUp':
    case 'w':
    case 'x':
      if (!repeat) doRotate(1);
      return true;
    case 'z':
      if (!repeat) doRotate(-1);
      return true;
    case ' ':
      if (!repeat) doHardDrop();
      return true;
    case 'c':
    case 'Shift':
      if (!repeat) doHold();
      return true;
    case 'f':
      if (!repeat) doOverdrive();
      return true;
    case 'b':
      if (!repeat) doBomb();
      return true;
    case 'e':
      if (!repeat) doLaser();
      return true;
    case 'p':
    case 'Escape':
      togglePause();
      return true;
    default:
      return false;
  }
}

function onKeyDown(event: KeyboardEvent): void {
  if (phase.value === 'closed') {
    detectSecret(event);
    return;
  }
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  if (event.target instanceof HTMLButtonElement && (event.key === 'Enter' || event.key === ' ')) return;
  ensureAudio();
  const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
  if (handleGameKey(key, event.repeat)) {
    event.preventDefault();
    event.stopPropagation();
  }
}

function onKeyUp(event: KeyboardEvent): void {
  if (phase.value === 'closed') return;
  const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
  if (key === 'ArrowLeft' || key === 'a') {
    held.left = false;
    releaseShift(-1);
  } else if (key === 'ArrowRight' || key === 'd') {
    held.right = false;
    releaseShift(1);
  } else if (key === 'ArrowDown' || key === 's') {
    held.down = false;
  }
}

function onWindowBlur(): void {
  if (phase.value === 'playing') togglePause();
  releaseInputs();
}

function touchShift(direction: number, pressed: boolean): void {
  ensureAudio();
  if (phase.value !== 'playing' || game?.upgradeChoices) return;
  if (direction === -1) held.left = pressed;
  else held.right = pressed;
  if (pressed) startShift(direction);
  else releaseShift(direction);
}

function touchSoftDrop(pressed: boolean): void {
  held.down = pressed && phase.value === 'playing';
}

function touchAction(action: () => void): void {
  ensureAudio();
  if (phase.value === 'playing' && !game?.upgradeChoices) action();
}

// ---------- Game loop ----------
function frame(now: number): void {
  const delta = Math.min(50, now - lastFrame);
  lastFrame = now;
  if (phase.value === 'playing' && game) {
    if (!game.upgradeChoices) autoRepeat(delta);
    tick(game, delta, held.down);
    processEvents();
    syncHud();
    if (phase.value === 'playing') soundtrack();
    if (hud.energy === 100) celebrate('charged', 'SOBRECARGA LISTA / Pulsa F');
    if (rank.value.score > 0) celebrate(rank.value.name, `NUEVO RANGO · ${rank.value.name.toUpperCase()}`);
  }
  updateEffects(delta);
  draw(now);
  rafId = requestAnimationFrame(frame);
}

function autoRepeat(delta: number): void {
  if (!game || !dasDirection) return;
  dasTimer += delta;
  if (dasTimer < DAS_MS) return;
  arrTimer += delta;
  while (arrTimer >= ARR_MS) {
    arrTimer -= ARR_MS;
    if (!move(game, dasDirection)) {
      arrTimer = 0;
      break;
    }
  }
}

function syncHud(): void {
  if (!game) return;
  hud.energy = game.energy;
  hud.time = game.time;
  hud.won = game.won;
  hud.missionLines = game.missionLines;
  hud.missionTarget = game.missionTarget;
  hud.missions = game.missions;
  hud.score = game.score;
  hud.level = game.level;
  hud.lines = game.lines;
  hud.combo = game.combo;
  hud.multiplier = scoreMultiplier(game);
  hud.fever = isFever(game) ? (game.feverUntil - game.time) / FEVER_DURATION_MS : 0;
  hud.previews = game.upgrades.previews;
  hud.slowMo = game.upgrades.slowMo;
  hud.bombs = game.upgrades.bombs;
  hud.lasers = game.upgrades.lasers;
  hud.shields = game.upgrades.shields;
  hud.choices = game.upgradeChoices;
  hud.danger = game.board.slice(HIDDEN_ROWS, HIDDEN_ROWS + 5).some(row => row.some(cell => cell !== null));
}

function processEvents(): void {
  if (!game) return;
  for (const event of drainEvents(game)) {
    switch (event.type) {
      case 'mission':
        popup('MISIÓN COMPLETA', { sub: `+${event.points} / +1 bomba`, tone: 'gold', y: 30, big: true });
        confetti(80);
        sfx.pick();
        break;
      case 'lock':
        event.cells.forEach(([x, y]) => cellFlashes.push({ x, y: y - HIDDEN_ROWS, life: 160 }));
        sfx.lock();
        break;
      case 'hardDrop': {
        if (event.distance <= 0) break;
        const color = PALETTE[event.piece].base;
        const tops = new Map<number, number>();
        event.cells.forEach(([x, y]) => tops.set(x, Math.min(tops.get(x) ?? y, y)));
        tops.forEach((y, x) => trails.push({ x, top: y - HIDDEN_ROWS - event.distance, bottom: y - HIDDEN_ROWS, life: 220, color }));
        event.cells.forEach(([x, y]) => burst((x + 0.5) * CELL, (y - HIDDEN_ROWS + 1) * CELL, 3, [color, '#ffffff'], 2.5));
        addShake(Math.min(6, 2 + event.distance * 0.25));
        sfx.drop();
        break;
      }
      case 'clear': {
        const visible = event.rows.map(row => row - HIDDEN_ROWS);
        const big = event.count === 4 || event.perfect || event.tSpin;
        const flashColor = event.perfect ? '#ffffff' : event.count === 4 ? '#facc15' : event.tSpin ? '#c084fc' : '#e0f2fe';
        visible.forEach(y => {
          rowFlashes.push({ y, life: 420, max: 420, color: flashColor });
          for (let x = 0; x < BOARD_WIDTH; x++) burst((x + 0.5) * CELL, (y + 0.5) * CELL, big ? 6 : 3, SPARK_COLORS, big ? 7 : 4.5);
        });
        const centerY = ((visible.reduce((total, y) => total + y, 0) / visible.length + 0.5) / VISIBLE_ROWS) * 100;
        const popupTone: Tone = event.perfect ? 'rainbow' : event.count === 4 ? 'gold' : event.tSpin ? 'violet' : 'white';
        popup(`${event.backToBack ? 'B2B ' : ''}${event.label}!`, { sub: `+${event.points.toLocaleString('es-BO')}`, tone: popupTone, y: centerY, big });
        if (event.combo >= 1) popup(`COMBO ×${event.combo + 1}`, { tone: event.combo >= 3 ? 'rainbow' : 'coral', y: Math.max(12, centerY - 16) });
        addShake([0, 2, 4, 7, 13][event.count] + (event.perfect ? 10 : 0));
        if (big) confetti(event.perfect ? 220 : 130);
        if (event.count === 4) hud.tetrises += 1;
        if (event.count === 4) celebrate('tetris', 'CUATRO DE UN GOLPE · Primer Tetris');
        if (event.perfect) celebrate('perfect', 'IMPECABLE · Tablero vacío');
        if (big && !reducedMotion && !calm.value) shockwaves.push({ x: BOARD_PX_W / 2, y: centerY / 100 * BOARD_PX_H, life: 600, max: 600, color: flashColor, radius: BOARD_PX_W });
        hud.maxCombo = Math.max(hud.maxCombo, event.combo + 1);
        scorePulse.value += 1;
        sfx.clear(event.count, event.combo);
        break;
      }
      case 'explode': {
        const x = (event.x + 0.5) * CELL;
        const y = (event.y - HIDDEN_ROWS + 0.5) * CELL;
        burst(x, y, 90, ['#f43f5e', '#fb923c', '#facc15', '#ffffff'], 9);
        shockwaves.push({ x, y, life: 500, max: 500, color: '#fb923c', radius: CELL * 3.5 });
        addShake(15);
        popup('¡BOOM!', { sub: event.points ? `+${event.points.toLocaleString('es-BO')}` : undefined, tone: 'coral', x: (event.x / BOARD_WIDTH) * 100, y: ((event.y - HIDDEN_ROWS) / VISIBLE_ROWS) * 100, big: true });
        scorePulse.value += 1;
        sfx.explode();
        break;
      }
      case 'laser':
        [VISIBLE_ROWS - 2, VISIBLE_ROWS - 1].forEach(y => {
          rowFlashes.push({ y, life: 500, max: 500, color: '#22d3ee' });
          for (let x = 0; x < BOARD_WIDTH; x++) burst((x + 0.5) * CELL, (y + 0.5) * CELL, 4, ['#22d3ee', '#a5f3fc', '#ffffff'], 6);
        });
        addShake(8);
        popup('¡LÁSER!', { sub: `+${event.points.toLocaleString('es-BO')}`, tone: 'teal', y: 85, big: true });
        scorePulse.value += 1;
        sfx.laser();
        break;
      case 'levelUp':
        popup(`NIVEL ${event.level}`, { sub: '¡Elige una mejora!', tone: 'gold', y: 30, big: true });
        confetti(160);
        sfx.levelUp();
        break;
      case 'fever':
        popup('FEVER ×2', { sub: '¡Puntos dobles!', tone: 'rainbow', y: 55, big: true });
        confetti(100);
        sfx.fever();
        break;
      case 'shield':
        popup('¡ESCUDO!', { sub: 'Segunda oportunidad', tone: 'teal', y: 40, big: true });
        shockwaves.push({ x: BOARD_PX_W / 2, y: BOARD_PX_H / 2, life: 700, max: 700, color: '#60a5fa', radius: BOARD_PX_H * 0.7 });
        addShake(12);
        sfx.shield();
        break;
      case 'gameOver':
        endGame();
        break;
    }
  }
}

// ---------- Effects ----------
function addShake(amount: number): void {
  if (!reducedMotion && !calm.value) shake = Math.max(shake, amount);
}

function burst(x: number, y: number, count: number, colors: string[], speed: number): void {
  const total = Math.ceil(count * ((reducedMotion || calm.value) ? 0.15 : 1));
  for (let index = 0; index < total; index++) {
    const angle = Math.random() * Math.PI * 2;
    const velocity = speed * (0.4 + Math.random() * 0.8);
    const max = 450 + Math.random() * 450;
    particles.push({
      x, y,
      vx: Math.cos(angle) * velocity,
      vy: Math.sin(angle) * velocity - speed * 0.4,
      life: max, max,
      color: colors[Math.floor(Math.random() * colors.length)],
      size: 2 + Math.random() * 3.5,
      gravity: 0.18,
    });
  }
}

function confetti(count: number): void {
  const total = Math.ceil(count * ((reducedMotion || calm.value) ? 0.15 : 1));
  for (let index = 0; index < total; index++) {
    const max = 900 + Math.random() * 900;
    particles.push({
      x: Math.random() * BOARD_PX_W,
      y: -10 - Math.random() * 60,
      vx: (Math.random() - 0.5) * 3,
      vy: 2 + Math.random() * 4,
      life: max, max,
      color: SPARK_COLORS[Math.floor(Math.random() * SPARK_COLORS.length)],
      size: 3 + Math.random() * 4,
      gravity: 0.06,
    });
  }
}

function popup(text: string, options: { sub?: string; tone?: Tone; x?: number; y?: number; big?: boolean } = {}): void {
  const id = ++popupId;
  popups.value = [...popups.value.slice(-5), {
    id, text, sub: options.sub, tone: options.tone ?? 'white',
    x: Math.min(80, Math.max(20, options.x ?? 50)), y: Math.min(88, Math.max(10, options.y ?? 50)), big: options.big ?? false,
  }];
  window.setTimeout(() => {
    popups.value = popups.value.filter(item => item.id !== id);
  }, 1400);
}

function updateEffects(delta: number): void {
  achievementLife = Math.max(0, achievementLife - delta);
  if (!achievementLife) achievement.value = '';
  if (calm.value || reducedMotion) shake = 0;
  const step = delta / 16.67;
  particles = particles.filter(particle => {
    particle.life -= delta;
    particle.vy += particle.gravity * step;
    particle.vx *= 0.985;
    particle.x += particle.vx * step;
    particle.y += particle.vy * step;
    return particle.life > 0 && particle.y < BOARD_PX_H + 40;
  });
  rowFlashes = rowFlashes.filter(flash => (flash.life -= delta) > 0);
  cellFlashes = cellFlashes.filter(flash => (flash.life -= delta) > 0);
  trails = trails.filter(trail => (trail.life -= delta) > 0);
  shockwaves = shockwaves.filter(wave => (wave.life -= delta) > 0);

  if (hud.displayScore !== hud.score) {
    const diff = hud.score - hud.displayScore;
    hud.displayScore = Math.abs(diff) < 1 ? hud.score : hud.displayScore + diff * Math.min(1, delta / 140);
  }

  shake *= Math.pow(0.86, step);
  if (shake < 0.2) shake = 0;
  if (boardShell.value) {
    boardShell.value.style.transform = shake
      ? `translate(${(Math.random() - 0.5) * shake}px, ${(Math.random() - 0.5) * shake}px)`
      : '';
  }
}

// ---------- Rendering ----------
function setupCanvas(canvas: HTMLCanvasElement | null, width: number, height: number, styleSize: boolean): void {
  if (!canvas) return;
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  if (styleSize) {
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
  }
}

function setupCanvases(): void {
  dpr = Math.min(2, window.devicePixelRatio || 1);
  setupCanvas(boardCanvas.value, BOARD_PX_W, BOARD_PX_H, false);
  setupCanvas(holdCanvas.value, 96, 64, true);
  setupCanvas(nextCanvas.value, 96, 5 * 58, true);
}

function roundedRect(ctx: CanvasRenderingContext2D, x: number, y: number, width: number, height: number, radius: number): void {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + width, y, x + width, y + height, radius);
  ctx.arcTo(x + width, y + height, x, y + height, radius);
  ctx.arcTo(x, y + height, x, y, radius);
  ctx.arcTo(x, y, x + width, y, radius);
  ctx.closePath();
}

function feverColors(x: number, y: number, now: number): Colors {
  const hue = Math.round(x * 24 + y * 12 + now / 6) % 360;
  return { base: `hsl(${hue}, 90%, 60%)`, light: `hsl(${hue}, 95%, 85%)`, dark: `hsl(${hue}, 80%, 34%)` };
}

function drawBlock(ctx: CanvasRenderingContext2D, px: number, py: number, size: number, colors: Colors, alpha = 1, glow = 0): void {
  const inset = size * 0.06;
  const side = size - inset * 2;
  const x = px + inset;
  const y = py + inset;
  const radius = size * 0.18;
  ctx.save();
  ctx.globalAlpha = alpha;
  if (glow) {
    ctx.shadowColor = colors.base;
    ctx.shadowBlur = glow;
  }
  const gradient = ctx.createLinearGradient(x, y, x + side, y + side);
  gradient.addColorStop(0, colors.light);
  gradient.addColorStop(0.45, colors.base);
  gradient.addColorStop(1, colors.dark);
  ctx.fillStyle = gradient;
  roundedRect(ctx, x, y, side, side, radius);
  ctx.fill();
  ctx.shadowBlur = 0;
  if (depth.value) {
    const bevel = size * 0.18;
    ctx.fillStyle = colors.dark;
    ctx.beginPath();
    ctx.moveTo(x + side, y); ctx.lineTo(x + side, y + side);
    ctx.lineTo(x, y + side); ctx.lineTo(x + bevel, y + side - bevel);
    ctx.lineTo(x + side - bevel, y + side - bevel); ctx.lineTo(x + side - bevel, y + bevel);
    ctx.closePath(); ctx.fill();
    ctx.fillStyle = colors.light;
    ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + side, y);
    ctx.lineTo(x + side - bevel, y + bevel); ctx.lineTo(x + bevel, y + bevel);
    ctx.lineTo(x + bevel, y + side - bevel); ctx.lineTo(x, y + side);
    ctx.closePath(); ctx.fill();
    ctx.fillStyle = colors.base;
    ctx.fillRect(x + bevel, y + bevel, side - bevel * 2, side - bevel * 2);
  }
  ctx.fillStyle = 'rgba(255,255,255,0.3)';
  roundedRect(ctx, x + side * 0.14, y + side * 0.1, side * 0.72, side * 0.2, radius * 0.6);
  ctx.fill();
  ctx.strokeStyle = 'rgba(255,255,255,0.22)';
  ctx.lineWidth = 1;
  roundedRect(ctx, x + 0.5, y + 0.5, side - 1, side - 1, radius);
  ctx.stroke();
  ctx.restore();
}

function drawBoard(now: number): void {
  const canvas = boardCanvas.value;
  const ctx = canvas?.getContext('2d');
  if (!ctx || !game) return;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, BOARD_PX_W, BOARD_PX_H);

  const background = ctx.createLinearGradient(0, 0, 0, BOARD_PX_H);
  background.addColorStop(0, 'rgba(10, 24, 42, 0.94)');
  background.addColorStop(1, 'rgba(3, 9, 20, 0.97)');
  ctx.fillStyle = background;
  ctx.fillRect(0, 0, BOARD_PX_W, BOARD_PX_H);

  // A subtle ambient glow leaves the playfield readable even during fever.
  const atmosphere = ctx.createRadialGradient(BOARD_PX_W / 2, BOARD_PX_H, 0, BOARD_PX_W / 2, BOARD_PX_H, BOARD_PX_H * 0.8);
  atmosphere.addColorStop(0, `hsla(${levelHue.value}, 85%, 55%, 0.12)`);
  atmosphere.addColorStop(1, 'transparent');
  ctx.fillStyle = atmosphere;
  ctx.fillRect(0, 0, BOARD_PX_W, BOARD_PX_H);

  ctx.strokeStyle = 'rgba(148, 163, 184, 0.07)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let x = 1; x < BOARD_WIDTH; x++) {
    ctx.moveTo(x * CELL + 0.5, 0);
    ctx.lineTo(x * CELL + 0.5, BOARD_PX_H);
  }
  for (let y = 1; y < VISIBLE_ROWS; y++) {
    ctx.moveTo(0, y * CELL + 0.5);
    ctx.lineTo(BOARD_PX_W, y * CELL + 0.5);
  }
  ctx.stroke();

  const fever = isFever(game);
  for (let y = HIDDEN_ROWS; y < BOARD_HEIGHT; y++) {
    for (let x = 0; x < BOARD_WIDTH; x++) {
      const cell = game.board[y][x];
      if (!cell) continue;
      const visibleY = y - HIDDEN_ROWS;
      drawBlock(ctx, x * CELL, visibleY * CELL, CELL, fever && !calm.value && !reducedMotion ? feverColors(x, visibleY, now) : PALETTE[cell]);
    }
  }

  trails.forEach(trail => {
    const alpha = trail.life / 220;
    const top = Math.max(0, trail.top) * CELL;
    const bottom = trail.bottom * CELL;
    if (bottom <= top) return;
    const gradient = ctx.createLinearGradient(0, top, 0, bottom);
    gradient.addColorStop(0, 'rgba(255,255,255,0)');
    gradient.addColorStop(1, trail.color);
    ctx.save();
    ctx.globalAlpha = alpha * 0.55;
    ctx.fillStyle = gradient;
    ctx.fillRect(trail.x * CELL + CELL * 0.2, top, CELL * 0.6, bottom - top);
    ctx.restore();
  });

  const active = game.active;
  if (active && phase.value !== 'over') {
    const colors = PALETTE[active.type];
    const landing = ghostY(game);
    const ghostCells = pieceCells({ ...active, y: landing });
    // Landing lanes communicate the drop path; they do not change game geometry.
    const columns = new Set(pieceCells(active).map(([x]) => x));
    ctx.save();
    ctx.globalAlpha = 0.045;
    ctx.fillStyle = colors.base;
    columns.forEach(x => ctx.fillRect(x * CELL, 0, CELL, BOARD_PX_H));
    ctx.restore();
    ctx.save();
    ghostCells.forEach(([x, y]) => {
      if (y < HIDDEN_ROWS) return;
      const py = (y - HIDDEN_ROWS) * CELL;
      ctx.fillStyle = colors.base;
      ctx.globalAlpha = 0.1;
      roundedRect(ctx, x * CELL + 3, py + 3, CELL - 6, CELL - 6, 5);
      ctx.fill();
      ctx.globalAlpha = 0.55;
      ctx.strokeStyle = colors.base;
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.globalAlpha = 0.75;
      ctx.fillRect(x * CELL + 8, py + CELL - 5, CELL - 16, 2);
    });
    ctx.restore();

    if (active.type === 'B') {
      const [[bombX, bombY]] = ghostCells;
      ctx.save();
      ctx.setLineDash([6, 5]);
      ctx.strokeStyle = 'rgba(251, 113, 133, 0.75)';
      ctx.lineWidth = 2;
      ctx.strokeRect((bombX - 2) * CELL + 1, (bombY - HIDDEN_ROWS - 2) * CELL + 1, CELL * 5 - 2, CELL * 5 - 2);
      ctx.restore();
    }

    const pulse = active.type === 'B' && !calm.value && !reducedMotion ? 18 + Math.sin(now / 160) * 6 : 14;
    pieceCells(active).forEach(([x, y]) => {
      if (y >= HIDDEN_ROWS) drawBlock(ctx, x * CELL, (y - HIDDEN_ROWS) * CELL, CELL, colors, 1, pulse);
    });
  }

  cellFlashes.forEach(flash => {
    if (flash.y < 0) return;
    ctx.save();
    ctx.globalAlpha = (flash.life / 160) * 0.7;
    ctx.fillStyle = '#ffffff';
    roundedRect(ctx, flash.x * CELL + 2, flash.y * CELL + 2, CELL - 4, CELL - 4, 6);
    ctx.fill();
    ctx.restore();
  });

  rowFlashes.forEach(flash => {
    const progress = flash.life / flash.max;
    ctx.save();
    ctx.globalAlpha = progress;
    ctx.shadowColor = flash.color;
    ctx.shadowBlur = 24;
    ctx.fillStyle = flash.color;
    const grow = (1 - progress) * CELL * 0.6;
    ctx.fillRect(0, flash.y * CELL - grow / 2 + CELL * (1 - progress) * 0.3, BOARD_PX_W, CELL * progress + grow);
    ctx.restore();
  });

  shockwaves.forEach(wave => {
    const progress = 1 - wave.life / wave.max;
    ctx.save();
    ctx.globalAlpha = 1 - progress;
    ctx.strokeStyle = wave.color;
    ctx.lineWidth = 6 * (1 - progress) + 1;
    ctx.shadowColor = wave.color;
    ctx.shadowBlur = 20;
    ctx.beginPath();
    ctx.arc(wave.x, wave.y, wave.radius * progress, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  });

  particles.forEach(particle => {
    ctx.globalAlpha = Math.max(0, particle.life / particle.max);
    ctx.fillStyle = particle.color;
    ctx.fillRect(particle.x - particle.size / 2, particle.y - particle.size / 2, particle.size, particle.size);
  });
  ctx.globalAlpha = 1;
}

function drawMini(ctx: CanvasRenderingContext2D, type: CellType, centerX: number, centerY: number, size: number, alpha: number): void {
  const filled: Array<[number, number]> = [];
  shapeOf(type).forEach((row, y) => row.forEach((value, x) => value && filled.push([x, y])));
  const minX = Math.min(...filled.map(([x]) => x));
  const maxX = Math.max(...filled.map(([x]) => x));
  const minY = Math.min(...filled.map(([, y]) => y));
  const maxY = Math.max(...filled.map(([, y]) => y));
  const offsetX = centerX - ((maxX - minX + 1) * size) / 2;
  const offsetY = centerY - ((maxY - minY + 1) * size) / 2;
  filled.forEach(([x, y]) => drawBlock(ctx, offsetX + (x - minX) * size, offsetY + (y - minY) * size, size, PALETTE[type], alpha));
}

function drawPreviews(): void {
  if (!game) return;
  const holdCtx = holdCanvas.value?.getContext('2d');
  if (holdCtx) {
    holdCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
    holdCtx.clearRect(0, 0, 96, 64);
    if (game.hold) drawMini(holdCtx, game.hold, 48, 32, 18, game.holdUsed ? 0.35 : 1);
  }
  const nextCtx = nextCanvas.value?.getContext('2d');
  if (nextCtx) {
    nextCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
    nextCtx.clearRect(0, 0, 96, 5 * 58);
    game.queue.slice(0, game.upgrades.previews).forEach((type, index) => {
      drawMini(nextCtx, type, 48, 29 + index * 58, index === 0 ? 19 : 15, index === 0 ? 1 : 0.75);
    });
  }
}

function draw(now: number): void {
  drawBoard(now);
  drawPreviews();
}

onMounted(() => {
  window.addEventListener('keydown', onKeyDown, true);
  window.addEventListener('keyup', onKeyUp, true);
  window.addEventListener('blur', onWindowBlur);
});

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeyDown, true);
  window.removeEventListener('keyup', onKeyUp, true);
  window.removeEventListener('blur', onWindowBlur);
  if (phase.value !== 'closed') closeGame();
  void audioContext?.close();
});
</script>

<template>
  <Teleport to="body">
    <Transition name="tetris-fade">
      <div
        v-if="isOpen"
        class="tetris-root"
        :class="{ 'is-fever': hud.fever > 0 && phase === 'playing', 'has-depth': depth, 'is-calm': calm || reducedMotion, 'is-lobby': phase === 'intro' }"
        :style="{ '--level-hue': levelHue }"
        role="dialog"
        aria-modal="true"
        aria-label="Maxi Tetris"
      >
        <div class="tetris-aurora" aria-hidden="true" />
        <div class="neon-stars" aria-hidden="true" />
        <div class="neon-grid" aria-hidden="true" />
        <div class="neon-orbit" aria-hidden="true" />

        <header class="tetris-topbar">
          <div class="tetris-logo">
            <span>MAXI</span><strong>TETRIS</strong><small class="neon-edition">HYPERDRIVE</small>
          </div>
          <div class="tetris-topbar-actions">
            <button type="button" class="tetris-icon-btn" :aria-pressed="music" title="Música sintetizada" aria-label="Música sintetizada" @click="toggleSetting('music')">♫</button>
            <button type="button" class="tetris-icon-btn" :aria-pressed="calm" title="Reducir efectos" aria-label="Reducir efectos" @click="toggleSetting('calm')"><Eye class="h-4 w-4" /></button>
            <button type="button" class="tetris-icon-btn" :aria-pressed="depth" title="Alternar relieve 3D" @click="toggleSetting('depth')">3D</button>
            <button type="button" class="tetris-icon-btn" :title="muted ? 'Activar sonido (M)' : 'Silenciar (M)'" @click="toggleMute">
              <VolumeX v-if="muted" class="h-4 w-4" />
              <Volume2 v-else class="h-4 w-4" />
            </button>
            <button
              v-if="phase === 'playing' || phase === 'paused'"
              type="button"
              class="tetris-icon-btn"
              :title="phase === 'paused' ? 'Continuar (P)' : 'Pausa (P)'"
              @click="togglePause"
            >
              <Play v-if="phase === 'paused'" class="h-4 w-4" />
              <Pause v-else class="h-4 w-4" />
            </button>
            <button type="button" class="tetris-icon-btn" title="Cerrar" @click="closeGame">
              <X class="h-4 w-4" />
            </button>
          </div>
        </header>

        <section v-if="phase === 'intro'" class="neon-lobby" aria-label="Elige tu partida">
          <div class="neon-hero">
            <p class="neon-kicker"><span /> EL OTRO LADO DE MAXICONECTA</p>
            <h1>ENCUENTRA<br />TU <em>FLOW.</em></h1>
            <p class="neon-description">Un bloque. Una reacción en cadena.<br />Convierte el caos en tu mejor jugada.</p>
            <div class="neon-features"><span><Flame /> Combos explosivos</span><span><Zap /> Poderes y mejoras</span></div>
            <div class="neon-sculpture" aria-hidden="true">
              <div v-for="(piece, index) in heroPieces" :key="piece" class="neon-piece" :class="`piece-${index}`" :style="{ '--piece-color': PALETTE[piece].base, '--piece-dark': PALETTE[piece].dark }">
                <template v-for="(row, y) in shapeOf(piece)" :key="y"><i v-for="(cell, x) in row" :key="x" :style="{ gridColumn: x + 1, gridRow: y + 1, visibility: cell ? 'visible' : 'hidden' }" /></template>
              </div>
              <div class="neon-sculpture-caption">PRECISIÓN. RITMO. REACCIÓN.</div>
            </div>
          </div>
          <div class="neon-launch">
            <p class="neon-kicker">01 / ELIGE TU DESAFÍO</p>
            <div class="neon-mode-list" role="group" aria-label="Modo de juego">
              <button v-for="(item, index) in modes" :key="item.id" :aria-pressed="mode === item.id" @click="mode = item.id">
                <span class="neon-mode-icon"><component :is="index === 0 ? Sparkles : index === 1 ? ChevronsDown : Zap" /></span>
                <span><strong>{{ item.name }}</strong><small>{{ item.copy }}</small></span><span class="neon-radio" />
              </button>
            </div>
            <p class="neon-kicker neon-theme-label">02 / TU ATMÓSFERA</p>
            <div class="neon-themes" role="group" aria-label="Atmósfera visual">
              <button v-for="item in themes" :key="item.id" :aria-pressed="theme === item.id" :style="{ '--swatch': item.color }" @click="setTheme(item.id)"><i />{{ item.name }}</button>
            </div>
            <button type="button" class="neon-launch-button" @click="startGame"><Play /> INICIAR PARTIDA <kbd>Enter</kbd></button>
            <p class="neon-launch-hint">← → mover · ↑ girar · Espacio soltar · P pausa</p>
          </div>
        </section>

        <main v-show="phase !== 'intro'" class="tetris-stage">
          <aside class="tetris-side">
            <section class="tetris-panel">
              <p class="tetris-label">Reserva <kbd>C</kbd></p>
              <canvas ref="holdCanvas" class="tetris-mini" />
            </section>

            <section class="tetris-panel tetris-score-panel">
              <p class="tetris-label">Puntaje</p>
              <p :key="scorePulse" class="tetris-score" :class="{ 'is-pulsing': scorePulse > 0 }">{{ formattedScore }}</p>
              <p class="tetris-best"><Trophy class="h-3.5 w-3.5" /> Récord {{ Math.max(hud.best, hud.score).toLocaleString('es-BO') }}</p>
              <div class="neon-rank"><span><Shield /> {{ rank.name }}</span><small>{{ nextRank ? `${nextRank.score.toLocaleString('es-BO')} → ${nextRank.name}` : 'Rango máximo' }}</small></div>
              <div class="tetris-progress"><div :style="{ width: `${rankProgress * 100}%` }" /></div>
              <div class="tetris-stat-grid">
                <div><span>Nivel</span><strong>{{ hud.level }}</strong></div>
                <div><span>Líneas</span><strong>{{ hud.lines }}</strong></div>
              </div>
              <div class="tetris-progress" :title="`${hud.lines % 10}/10 líneas para la próxima mejora`">
                <div :style="{ width: `${levelProgress * 100}%` }" />
              </div>
              <p class="tetris-hint">Mejora cada {{ LINES_PER_LEVEL }} líneas</p>
            </section>

            <section class="tetris-panel">
              <p class="tetris-label">Racha</p>
              <div class="tetris-combo">
                <Flame class="h-5 w-5" :class="hud.combo >= 1 ? 'text-orange-400' : 'text-slate-600'" />
                <strong>{{ Math.max(0, hud.combo + 1) }}</strong>
                <span>× {{ hud.multiplier.toFixed(2) }}</span>
              </div>
              <div class="tetris-fever" :class="{ 'is-active': hud.fever > 0 }">
                <div :style="{ width: `${hud.fever > 0 ? hud.fever * 100 : Math.min(100, (Math.max(0, hud.combo + 1) / 4) * 100)}%` }" />
              </div>
              <p class="tetris-hint">{{ hud.fever > 0 ? '¡FEVER! Puntos ×2' : '4 limpiezas seguidas = FEVER' }}</p>
            </section>
          </aside>

          <section class="tetris-board-wrap">
            <div class="tetris-session"><span>{{ modes.find(item => item.id === mode)?.name }}</span><strong>{{ clockText }}</strong><span>{{ mode === 'sprint' ? `${Math.min(40, hud.lines)}/40` : `x${hud.multiplier.toFixed(2)}` }}</span></div>
            <div class="tetris-mobile-hud"><span>{{ formattedScore }} pts / M{{ hud.missions + 1 }}: {{ hud.missionLines }}/{{ hud.missionTarget }}</span><button :disabled="hud.energy < 100 || hud.fever > 0 || phase !== 'playing' || !!hud.choices" @click="touchAction(doOverdrive)">Sobrecarga {{ hud.energy }}%</button></div>
            <div ref="boardShell" class="tetris-board-shell" :class="{ 'is-danger': hud.danger && phase === 'playing' }">
              <canvas ref="boardCanvas" class="tetris-board" />
              <div v-if="hud.fever > 0 && phase === 'playing'" class="neon-fever-label"><Flame /> HYPERDRIVE <strong>×2</strong></div>

              <div class="tetris-popups" aria-live="polite">
                <div
                  v-for="item in popups"
                  :key="item.id"
                  class="tetris-popup"
                  :class="[`tone-${item.tone}`, { 'is-big': item.big }]"
                  :style="{ left: `${item.x}%`, top: `${item.y}%` }"
                >
                  <strong>{{ item.text }}</strong>
                  <span v-if="item.sub">{{ item.sub }}</span>
                </div>
              </div>

              <Transition name="tetris-pop">
                <div v-if="phase === 'playing' && hud.choices" class="tetris-overlay">
                  <p class="tetris-eyebrow">¡Nivel {{ hud.level }} alcanzado!</p>
                  <h3 class="tetris-overlay-title">Elige una mejora</h3>
                  <div class="tetris-upgrades">
                    <button
                      v-for="(id, index) in hud.choices"
                      :key="id"
                      type="button"
                      class="tetris-upgrade"
                      :style="{ '--card-color': UPGRADE_COLORS[id], animationDelay: `${index * 90}ms` }"
                      @click="pickUpgrade(id)"
                    >
                      <span class="tetris-upgrade-key">{{ index + 1 }}</span>
                      <span class="tetris-upgrade-icon"><component :is="UPGRADE_ICONS[id]" class="h-5 w-5" /></span>
                      <span class="tetris-upgrade-copy">
                        <strong>{{ UPGRADES[id].name }}</strong>
                        <small>{{ UPGRADES[id].description }}</small>
                      </span>
                    </button>
                  </div>
                </div>
              </Transition>

              <div v-if="phase === 'paused'" class="tetris-overlay">
                <div class="neon-pause-icon"><Pause /></div>
                <h3 class="tetris-overlay-title">Pausa</h3>
                <p class="tetris-overlay-copy">El siguiente gran movimiento puede esperar.</p>
                <button type="button" class="tetris-cta" @click="togglePause">Continuar <kbd>P</kbd></button>
                <button type="button" class="tetris-ghost-btn" @click="returnToLobby">Cambiar de desafío</button>
                <button type="button" class="tetris-ghost-btn" @click="closeGame">Salir <kbd>Esc</kbd></button>
              </div>

              <div v-if="phase === 'over'" class="tetris-overlay">
                <div class="neon-result-medal"><Trophy /><span>{{ rank.name }}</span></div>
                <p class="tetris-eyebrow">{{ hud.newBest ? '¡Nuevo récord!' : hud.won ? 'Desafío completado' : 'Fin del juego' }}</p>
                <h3 class="tetris-overlay-title" :class="{ 'is-record': hud.newBest }">{{ hud.score.toLocaleString('es-BO') }}</h3>
                <p class="tetris-hint">{{ clockText }} / {{ hud.missions }} misiones completadas</p>
                <div class="tetris-summary">
                  <div><span>Nivel</span><strong>{{ hud.level }}</strong></div>
                  <div><span>Líneas</span><strong>{{ hud.lines }}</strong></div>
                  <div><span>Tetris</span><strong>{{ hud.tetrises }}</strong></div>
                  <div><span>Mejor combo</span><strong>{{ hud.maxCombo }}</strong></div>
                </div>
                <button type="button" class="tetris-cta" @click="startGame">Otra vez <kbd>Enter</kbd></button>
                <button type="button" class="tetris-ghost-btn" @click="returnToLobby">Elegir otro desafío</button>
                <button type="button" class="tetris-ghost-btn" @click="closeGame">Salir <kbd>Esc</kbd></button>
              </div>
            </div>
          </section>

          <aside class="tetris-side">
            <section class="tetris-panel">
              <p class="tetris-label">Siguientes</p>
              <canvas ref="nextCanvas" class="tetris-mini" />
            </section>

            <section class="tetris-panel">
              <p class="tetris-label">Sobrecarga <kbd>F</kbd></p>
              <button class="tetris-overdrive" :disabled="hud.energy < 100 || hud.fever > 0 || phase !== 'playing' || !!hud.choices" @click="touchAction(doOverdrive)"><Zap class="h-4 w-4" /> {{ hud.energy >= 100 ? 'ACTIVAR x2' : `${hud.energy}%` }}</button>
              <div class="tetris-progress"><div :style="{ width: `${hud.energy}%` }" /></div>
              <p class="tetris-hint">Carga con líneas. Activa 8 s de puntos dobles.</p>
              <p class="tetris-label" style="margin-top: 14px">Misión {{ hud.missions + 1 }}</p>
              <p class="tetris-hint">Líneas: {{ hud.missionLines }}/{{ hud.missionTarget }}</p>
              <div class="tetris-progress"><div :style="{ width: `${hud.missionLines / hud.missionTarget * 100}%` }" /></div>
              <p class="tetris-hint">+{{ 500 * (hud.missions + 1) }} puntos base y 1 bomba</p>
              <p class="tetris-label" style="margin-top: 14px">Mejoras</p>
              <ul class="tetris-buffs">
                <li :class="{ 'is-on': hud.bombs > 0 }"><Bomb class="h-4 w-4" /> Bombas <kbd>B</kbd><strong>{{ hud.bombs }}</strong></li>
                <li :class="{ 'is-on': hud.lasers > 0 }"><Zap class="h-4 w-4" /> Láser <kbd>E</kbd><strong>{{ hud.lasers }}</strong></li>
                <li :class="{ 'is-on': hud.shields > 0 }"><Shield class="h-4 w-4" /> Escudos<strong>{{ hud.shields }}</strong></li>
                <li :class="{ 'is-on': hud.slowMo > 0 }"><Snail class="h-4 w-4" /> Lentitud<strong>{{ hud.slowMo }}</strong></li>
                <li :class="{ 'is-on': hud.previews > 3 }"><Eye class="h-4 w-4" /> Visión<strong>{{ hud.previews }}</strong></li>
              </ul>
            </section>

            <section class="tetris-panel tetris-controls">
              <p class="tetris-label">Controles</p>
              <p><kbd>←</kbd><kbd>→</kbd> mover · <kbd>↓</kbd> bajar</p>
              <p><kbd>↑</kbd>/<kbd>X</kbd> girar · <kbd>Z</kbd> girar ⟲</p>
              <p><kbd>Espacio</kbd> caída · <kbd>C</kbd> reserva</p>
              <p><kbd>P</kbd> pausa · <kbd>M</kbd> sonido</p>
            </section>
          </aside>
        </main>

        <Transition name="neon-toast"><div v-if="achievement && phase !== 'intro'" class="neon-achievement" role="status"><Trophy /><div><small>BIEN JUGADO</small><strong>{{ achievement }}</strong></div></div></Transition>
        <nav v-show="phase !== 'intro'" class="tetris-touch" aria-label="Controles táctiles">
          <button type="button" aria-label="Mover a la izquierda" @pointerdown.prevent="touchShift(-1, true)" @pointerup="touchShift(-1, false)" @pointerleave="touchShift(-1, false)" @pointercancel="releaseInputs"><ArrowLeft class="h-5 w-5" /></button>
          <button type="button" aria-label="Bajar pieza" @pointerdown.prevent="touchSoftDrop(true)" @pointerup="touchSoftDrop(false)" @pointerleave="touchSoftDrop(false)" @pointercancel="releaseInputs"><ArrowDown class="h-5 w-5" /></button>
          <button type="button" aria-label="Mover a la derecha" @pointerdown.prevent="touchShift(1, true)" @pointerup="touchShift(1, false)" @pointerleave="touchShift(1, false)" @pointercancel="releaseInputs"><ArrowRight class="h-5 w-5" /></button>
          <button type="button" aria-label="Girar a la izquierda" @pointerdown.prevent="touchAction(() => doRotate(-1))"><RotateCcw class="h-5 w-5" /></button>
          <button type="button" aria-label="Girar a la derecha" @pointerdown.prevent="touchAction(() => doRotate(1))"><RotateCw class="h-5 w-5" /></button>
          <button type="button" class="is-primary" aria-label="Soltar pieza" @pointerdown.prevent="touchAction(doHardDrop)"><ChevronsDown class="h-5 w-5" /></button>
          <button type="button" aria-label="Reservar pieza" @pointerdown.prevent="touchAction(doHold)"><Archive class="h-5 w-5" /></button>
          <button type="button" :disabled="hud.bombs === 0" aria-label="Usar bomba" @pointerdown.prevent="touchAction(doBomb)"><Bomb class="h-5 w-5" /></button>
          <button type="button" :disabled="hud.lasers === 0" aria-label="Usar laser" @pointerdown.prevent="touchAction(doLaser)"><Zap class="h-5 w-5" /></button>
        </nav>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.tetris-mobile-hud { display: none; }
.tetris-overlay { overflow-y: auto; }
.tetris-session { display: flex; justify-content: space-between; align-items: center; color: #a5f3fc; font: 700 11px monospace; padding: 6px 12px; }
.tetris-session strong { font-size: 18px; color: white; font-variant-numeric: tabular-nums; }
.has-depth .tetris-board-shell { box-shadow: 6px 7px 0 #111e36, 9px 11px 0 #060c19, 0 0 50px var(--accent-soft); border-bottom: 3px solid #45617c; }
.tetris-modes { display: grid; gap: 7px; width: 100%; margin: 0 0 16px; }
.tetris-modes button { padding: 10px 12px; text-align: left; border: 1px solid #334155; border-radius: 10px; background: #0f172a; color: #cbd5e1; }
.tetris-modes button[aria-pressed="true"] { border-color: #22d3ee; background: #123044; box-shadow: inset 3px 0 #22d3ee; }
.tetris-modes strong, .tetris-modes small { display: block; }
.tetris-modes small { font-size: 10px; margin-top: 3px; color: #94a3b8; }
.tetris-overdrive { display: flex; align-items: center; justify-content: center; gap: 5px; width: 100%; padding: 9px 3px; border-radius: 8px; color: #082f49; background: #67e8f9; font-size: 11px; font-weight: 900; }
.tetris-overdrive:disabled { color: #94a3b8; background: #1e293b; }
.tetris-root button:focus-visible { outline: 2px solid #facc15; outline-offset: 3px; }

.tetris-root {
  --accent: hsl(var(--level-hue), 85%, 60%);
  --accent-soft: hsla(var(--level-hue), 85%, 60%, 0.35);
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: radial-gradient(circle at 20% 10%, #0f2f3a 0%, #060d1c 45%, #03060f 100%);
  color: #e2e8f0;
  font-family: "Aptos", "Segoe UI Variable", "Segoe UI", sans-serif;
  user-select: none;
}

.tetris-aurora {
  position: absolute;
  inset: -20%;
  pointer-events: none;
  background:
    radial-gradient(circle at 25% 30%, hsla(var(--level-hue), 90%, 55%, 0.22), transparent 40%),
    radial-gradient(circle at 80% 70%, rgba(239, 118, 91, 0.18), transparent 42%),
    radial-gradient(circle at 60% 15%, rgba(8, 127, 115, 0.22), transparent 38%);
  filter: blur(30px);
  animation: tetris-aurora 14s ease-in-out infinite alternate;
}

.tetris-root.is-fever .tetris-aurora {
  background:
    radial-gradient(circle at 25% 30%, rgba(244, 63, 94, 0.3), transparent 40%),
    radial-gradient(circle at 75% 65%, rgba(250, 204, 21, 0.25), transparent 40%),
    radial-gradient(circle at 50% 10%, rgba(192, 132, 252, 0.3), transparent 40%);
  animation-duration: 3s;
}

.tetris-topbar {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 22px;
}

.tetris-logo {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-weight: 900;
  letter-spacing: 0.22em;
}

.tetris-logo span {
  font-size: 0.8rem;
  color: #5eead4;
}

.tetris-logo strong {
  font-size: 1.35rem;
  background: linear-gradient(90deg, #22d3ee, #c084fc, #fb7185, #facc15);
  background-size: 200% auto;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  animation: tetris-shine 4s linear infinite;
}

.tetris-topbar-actions {
  display: flex;
  gap: 8px;
}

.tetris-icon-btn {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.6);
  color: #e2e8f0;
  transition: transform 0.15s ease, border-color 0.15s ease;
}

.tetris-icon-btn:hover {
  transform: translateY(-1px);
  border-color: var(--accent);
}

.tetris-stage {
  position: relative;
  flex: 1;
  display: grid;
  grid-template-columns: minmax(150px, 210px) auto minmax(150px, 210px);
  justify-content: center;
  align-items: start;
  gap: 22px;
  padding: 0 22px 18px;
  min-height: 0;
}

.tetris-side {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tetris-panel {
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 18px;
  background: linear-gradient(160deg, rgba(15, 23, 42, 0.75), rgba(2, 6, 23, 0.6));
  padding: 12px 14px;
  backdrop-filter: blur(8px);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
}

.tetris-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #94a3b8;
  margin-bottom: 6px;
}

.tetris-mini {
  display: block;
  margin: 0 auto;
}

.tetris-score {
  font-size: 1.9rem;
  font-weight: 900;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
  color: #fff;
  text-shadow: 0 0 18px var(--accent-soft);
}

.tetris-score.is-pulsing {
  animation: tetris-bump 0.35s ease-out;
}

.tetris-best {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 2px;
  font-size: 0.75rem;
  color: #facc15;
}

.tetris-stat-grid,
.tetris-summary {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  margin-top: 10px;
}

.tetris-stat-grid div,
.tetris-summary div {
  border-radius: 12px;
  background: rgba(148, 163, 184, 0.08);
  padding: 6px 8px;
}

.tetris-stat-grid span,
.tetris-summary span {
  display: block;
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: #94a3b8;
}

.tetris-stat-grid strong,
.tetris-summary strong {
  font-size: 1.15rem;
  font-variant-numeric: tabular-nums;
}

.tetris-progress,
.tetris-fever {
  height: 8px;
  margin-top: 10px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.14);
  overflow: hidden;
}

.tetris-progress div {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--accent), #facc15);
  box-shadow: 0 0 12px var(--accent);
  transition: width 0.35s cubic-bezier(0.2, 0.9, 0.3, 1.3);
}

.tetris-fever div {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #fb923c, #fb7185);
  transition: width 0.25s ease;
}

.tetris-fever.is-active div {
  background: linear-gradient(90deg, #22d3ee, #c084fc, #fb7185, #facc15, #22d3ee);
  background-size: 200% auto;
  animation: tetris-shine 1s linear infinite;
  transition: none;
}

.tetris-hint {
  margin-top: 6px;
  font-size: 0.7rem;
  color: #64748b;
}

.tetris-combo {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tetris-combo strong {
  font-size: 1.6rem;
  font-weight: 900;
}

.tetris-combo span {
  margin-left: auto;
  border-radius: 999px;
  background: rgba(250, 204, 21, 0.14);
  padding: 2px 8px;
  font-size: 0.75rem;
  font-weight: 800;
  color: #facc15;
}

.tetris-board-wrap {
  display: flex;
  justify-content: center;
}

.tetris-board-shell {
  position: relative;
  height: min(calc(100vh - 110px), 680px);
  aspect-ratio: 1 / 2;
  border-radius: 20px;
  padding: 6px;
  background: linear-gradient(160deg, hsla(var(--level-hue), 85%, 60%, 0.55), rgba(15, 23, 42, 0.8) 40%, rgba(239, 118, 91, 0.45));
  box-shadow: 0 0 40px var(--accent-soft), 0 30px 80px rgba(0, 0, 0, 0.55);
  transition: box-shadow 0.4s ease;
  will-change: transform;
}

.tetris-root.is-fever .tetris-board-shell {
  background: linear-gradient(90deg, #22d3ee, #c084fc, #fb7185, #facc15, #4ade80, #22d3ee);
  background-size: 300% 100%;
  animation: tetris-shine 2s linear infinite;
  box-shadow: 0 0 60px rgba(250, 204, 21, 0.45), 0 30px 80px rgba(0, 0, 0, 0.55);
}

.tetris-board-shell.is-danger {
  box-shadow: 0 0 46px rgba(244, 63, 94, 0.6), 0 30px 80px rgba(0, 0, 0, 0.55);
  animation: tetris-danger 0.9s ease-in-out infinite;
}

.tetris-board {
  display: block;
  width: 100%;
  height: 100%;
  border-radius: 15px;
}

.tetris-popups {
  position: absolute;
  inset: 6px;
  z-index: 5;
  pointer-events: none;
  overflow: hidden;
  border-radius: 15px;
}

.tetris-popup {
  position: absolute;
  display: flex;
  flex-direction: column;
  align-items: center;
  transform: translate(-50%, -50%);
  white-space: nowrap;
  animation: tetris-popup 1.35s cubic-bezier(0.2, 0.9, 0.3, 1.2) forwards;
}

.tetris-popup strong {
  font-size: 1.15rem;
  font-weight: 900;
  letter-spacing: 0.06em;
}

.tetris-popup span {
  font-size: 0.95rem;
  font-weight: 800;
  color: #fef9c3;
  text-shadow: 0 2px 10px rgba(0, 0, 0, 0.6);
}

.tetris-popup.is-big strong {
  font-size: 1.9rem;
}

.tone-white strong { color: #fff; text-shadow: 0 0 14px rgba(255, 255, 255, 0.7); }
.tone-gold strong { color: #facc15; text-shadow: 0 0 18px rgba(250, 204, 21, 0.8); }
.tone-teal strong { color: #5eead4; text-shadow: 0 0 18px rgba(45, 212, 191, 0.8); }
.tone-coral strong { color: #fb7185; text-shadow: 0 0 18px rgba(251, 113, 133, 0.8); }
.tone-violet strong { color: #d8b4fe; text-shadow: 0 0 18px rgba(192, 132, 252, 0.85); }
.tone-rainbow strong {
  background: linear-gradient(90deg, #22d3ee, #c084fc, #fb7185, #facc15, #4ade80);
  background-size: 200% auto;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  filter: drop-shadow(0 0 10px rgba(250, 204, 21, 0.6));
  animation: tetris-shine 0.8s linear infinite;
}

.tetris-overlay {
  position: absolute;
  inset: 6px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  border-radius: 15px;
  background: rgba(2, 6, 23, 0.78);
  backdrop-filter: blur(6px);
  padding: 18px;
  text-align: center;
}

.tetris-eyebrow {
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: #5eead4;
}

.tetris-overlay-title {
  font-size: 1.8rem;
  font-weight: 900;
  color: #fff;
}

.tetris-overlay-title.is-hero,
.tetris-overlay-title.is-record {
  font-size: 2.2rem;
  background: linear-gradient(90deg, #22d3ee, #c084fc, #fb7185, #facc15);
  background-size: 200% auto;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  animation: tetris-shine 3s linear infinite;
}

.tetris-overlay-copy {
  max-width: 240px;
  font-size: 0.85rem;
  color: #cbd5e1;
}

.tetris-cta,
.tetris-ghost-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border-radius: 999px;
  padding: 10px 22px;
  font-weight: 800;
  transition: transform 0.15s ease;
}

.tetris-cta {
  background: linear-gradient(90deg, #087f73, #22d3ee);
  color: #fff;
  box-shadow: 0 0 24px rgba(34, 211, 238, 0.45);
  animation: tetris-breathe 1.6s ease-in-out infinite;
}

.tetris-ghost-btn {
  border: 1px solid rgba(148, 163, 184, 0.3);
  color: #cbd5e1;
}

.tetris-cta:hover,
.tetris-ghost-btn:hover {
  transform: scale(1.05);
}

.tetris-upgrades {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.tetris-upgrade {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid color-mix(in srgb, var(--card-color) 55%, transparent);
  border-radius: 16px;
  background: linear-gradient(135deg, color-mix(in srgb, var(--card-color) 22%, #0f172a), #020617);
  padding: 12px;
  text-align: left;
  box-shadow: 0 0 18px color-mix(in srgb, var(--card-color) 30%, transparent);
  animation: tetris-card-in 0.45s cubic-bezier(0.2, 0.9, 0.3, 1.3) both;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.tetris-upgrade:hover {
  transform: translateY(-2px) scale(1.02);
  box-shadow: 0 0 30px color-mix(in srgb, var(--card-color) 60%, transparent);
}

.tetris-upgrade-key {
  position: absolute;
  top: 6px;
  right: 8px;
  font-size: 0.7rem;
  font-weight: 900;
  color: #64748b;
}

.tetris-upgrade-icon {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 38px;
  height: 38px;
  border-radius: 12px;
  background: color-mix(in srgb, var(--card-color) 25%, transparent);
  color: var(--card-color);
}

.tetris-upgrade-copy strong {
  display: block;
  font-size: 0.95rem;
  color: #fff;
}

.tetris-upgrade-copy small {
  display: block;
  font-size: 0.72rem;
  line-height: 1.35;
  color: #cbd5e1;
}

.tetris-buffs {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.tetris-buffs li {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 0.8rem;
  color: #64748b;
  transition: color 0.2s ease;
}

.tetris-buffs li.is-on {
  color: #e2e8f0;
}

.tetris-buffs li strong {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}

.tetris-buffs li.is-on strong {
  color: #facc15;
}

.tetris-controls p {
  font-size: 0.72rem;
  line-height: 1.9;
  color: #94a3b8;
}

kbd {
  display: inline-block;
  min-width: 1.4em;
  border: 1px solid rgba(148, 163, 184, 0.35);
  border-bottom-width: 2px;
  border-radius: 6px;
  padding: 0 4px;
  font-family: inherit;
  font-size: 0.68rem;
  font-weight: 700;
  line-height: 1.5;
  text-align: center;
  color: #e2e8f0;
  background: rgba(148, 163, 184, 0.1);
}

.tetris-touch {
  display: none;
}

@media (max-width: 900px) {
  .tetris-mobile-hud { display: flex; justify-content: space-between; align-items: center; gap: 8px; color: #a5f3fc; font-size: 10px; padding: 4px 0 8px; }
  .tetris-mobile-hud button { padding: 6px; background: #155e75; border-radius: 6px; }
  .tetris-mobile-hud button:disabled { opacity: .5; }
  .tetris-modes { gap: 4px; margin-bottom: 8px; }
  .tetris-modes button { padding: 6px 9px; }

  .tetris-stage {
    grid-template-columns: auto;
    gap: 10px;
    padding: 0 10px 8px;
  }

  .tetris-side {
    display: none;
  }

  .tetris-board-shell {
    height: min(calc(100vh - 230px), 620px);
  }

  .tetris-touch {
    position: relative;
    display: grid;
    grid-template-columns: repeat(9, 1fr);
    gap: 6px;
    padding: 8px 10px 14px;
  }

  .tetris-touch button {
    display: grid;
    place-items: center;
    height: 48px;
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 14px;
    background: rgba(15, 23, 42, 0.75);
    color: #e2e8f0;
    touch-action: none;
  }

  .tetris-touch button.is-primary {
    background: linear-gradient(135deg, #087f73, #22d3ee);
  }

  .tetris-touch button:disabled {
    opacity: 0.35;
  }
}

.tetris-fade-enter-active,
.tetris-fade-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}

.tetris-fade-enter-from,
.tetris-fade-leave-to {
  opacity: 0;
  transform: scale(1.03);
}

.tetris-pop-enter-active {
  transition: opacity 0.25s ease, transform 0.35s cubic-bezier(0.2, 0.9, 0.3, 1.3);
}

.tetris-pop-enter-from {
  opacity: 0;
  transform: scale(0.85);
}

@keyframes tetris-popup {
  0% { opacity: 0; transform: translate(-50%, -30%) scale(0.5); }
  15% { opacity: 1; transform: translate(-50%, -50%) scale(1.18); }
  30% { transform: translate(-50%, -50%) scale(1); }
  75% { opacity: 1; }
  100% { opacity: 0; transform: translate(-50%, -140%) scale(0.95); }
}

@keyframes tetris-shine {
  to { background-position: 200% center; }
}

@keyframes tetris-bump {
  0% { transform: scale(1); }
  40% { transform: scale(1.18); color: #facc15; }
  100% { transform: scale(1); }
}

@keyframes tetris-aurora {
  from { transform: translate3d(-3%, -2%, 0) rotate(0deg); }
  to { transform: translate3d(3%, 2%, 0) rotate(8deg); }
}

@keyframes tetris-danger {
  50% { box-shadow: 0 0 70px rgba(244, 63, 94, 0.85), 0 30px 80px rgba(0, 0, 0, 0.55); }
}

@keyframes tetris-breathe {
  50% { box-shadow: 0 0 40px rgba(34, 211, 238, 0.7); transform: scale(1.03); }
}

@keyframes tetris-card-in {
  from { opacity: 0; transform: translateY(18px) scale(0.92); }
}

@media (prefers-reduced-motion: reduce) {
  .tetris-aurora,
  .tetris-cta,
  .tetris-board-shell,
  .tetris-logo strong {
    animation: none !important;
  }
}
</style>

<style scoped src="./tetris-neon.css"></style>

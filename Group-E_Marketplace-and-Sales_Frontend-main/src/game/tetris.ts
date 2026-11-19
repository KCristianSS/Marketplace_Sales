export type PieceType = 'I' | 'O' | 'T' | 'S' | 'Z' | 'J' | 'L';
export type CellType = PieceType | 'B';
export type GameMode = 'arcade' | 'sprint' | 'blitz';
export const BLITZ_DURATION = 120000;
export type Cell = CellType | null;
export type UpgradeId = 'slowMo' | 'multiplier' | 'vision' | 'bomb' | 'laser' | 'shield';

export const BOARD_WIDTH = 10;
export const BOARD_HEIGHT = 22;
export const HIDDEN_ROWS = 2;
export const LINES_PER_LEVEL = 10;
export const FEVER_COMBO = 4;
export const FEVER_DURATION_MS = 8000;
const LOCK_DELAY_MS = 500;
const MAX_LOCK_RESETS = 15;
const PIECES: PieceType[] = ['I', 'O', 'T', 'S', 'Z', 'J', 'L'];

export interface ActivePiece {
  type: CellType;
  rotation: number;
  x: number;
  y: number;
}

export interface Upgrades {
  slowMo: number;
  multiplier: number;
  previews: number;
  bombs: number;
  lasers: number;
  shields: number;
}

export type GameEvent =
  | { type: 'clear'; rows: number[]; count: number; label: string; points: number; tSpin: boolean; perfect: boolean; combo: number; backToBack: boolean }
  | { type: 'lock'; cells: Array<[number, number]> }
  | { type: 'hardDrop'; piece: CellType; distance: number; cells: Array<[number, number]> }
  | { type: 'explode'; x: number; y: number; cleared: number; points: number }
  | { type: 'laser'; rows: number[]; points: number }
  | { type: 'levelUp'; level: number }
  | { type: 'fever' }
  | { type: 'shield' }
  | { type: 'mission'; points: number }
  | { type: 'gameOver' };

export interface GameState {
  mode: GameMode;
  won: boolean;
  energy: number;
  missionLines: number;
  missionTarget: number;
  missions: number;
  board: Cell[][];
  active: ActivePiece | null;
  hold: PieceType | null;
  holdUsed: boolean;
  queue: PieceType[];
  bag: PieceType[];
  score: number;
  lines: number;
  level: number;
  combo: number;
  backToBack: boolean;
  over: boolean;
  time: number;
  feverUntil: number;
  upgrades: Upgrades;
  upgradeChoices: UpgradeId[] | null;
  events: GameEvent[];
  gravityAccumulator: number;
  lockTimer: number;
  lockResets: number;
  lastMoveWasRotation: boolean;
  bombArmed: boolean;
  random: () => number;
}

export interface UpgradeInfo {
  id: UpgradeId;
  name: string;
  description: string;
}

export const UPGRADES: Record<UpgradeId, UpgradeInfo> = {
  slowMo: { id: 'slowMo', name: 'Cámara lenta', description: 'Las piezas caen un 20% más lento.' },
  multiplier: { id: 'multiplier', name: 'Multiplicador', description: '+25% a todos los puntos ganados.' },
  vision: { id: 'vision', name: 'Clarividencia', description: 'Ves una pieza más en la cola (máx. 5).' },
  bomb: { id: 'bomb', name: 'Bomba', description: '+2 bombas [B]: la pieza explota y limpia un área 5×5.' },
  laser: { id: 'laser', name: 'Láser', description: '+1 láser [E]: borra al instante las 2 filas inferiores.' },
  shield: { id: 'shield', name: 'Escudo', description: '+1 escudo: si te llenas, limpia 6 filas y sigues jugando.' },
};

const BASE_SHAPES: Record<CellType, number[][]> = {
  I: [[0, 0, 0, 0], [1, 1, 1, 1], [0, 0, 0, 0], [0, 0, 0, 0]],
  O: [[1, 1], [1, 1]],
  T: [[0, 1, 0], [1, 1, 1], [0, 0, 0]],
  S: [[0, 1, 1], [1, 1, 0], [0, 0, 0]],
  Z: [[1, 1, 0], [0, 1, 1], [0, 0, 0]],
  J: [[1, 0, 0], [1, 1, 1], [0, 0, 0]],
  L: [[0, 0, 1], [1, 1, 1], [0, 0, 0]],
  B: [[1]],
};

function rotateMatrix(matrix: number[][]): number[][] {
  const size = matrix.length;
  return matrix.map((row, y) => row.map((_, x) => matrix[size - 1 - x][y]));
}

const ROTATIONS = Object.fromEntries(
  (Object.keys(BASE_SHAPES) as CellType[]).map(type => {
    const states = [BASE_SHAPES[type]];
    for (let index = 1; index < 4; index++) states.push(rotateMatrix(states[index - 1]));
    return [type, states];
  }),
) as Record<CellType, number[][][]>;

// SRS kick offsets use y-up coordinates; they are inverted when applied to the y-down board.
const JLSTZ_KICKS: Record<string, Array<[number, number]>> = {
  '0>1': [[0, 0], [-1, 0], [-1, 1], [0, -2], [-1, -2]],
  '1>0': [[0, 0], [1, 0], [1, -1], [0, 2], [1, 2]],
  '1>2': [[0, 0], [1, 0], [1, -1], [0, 2], [1, 2]],
  '2>1': [[0, 0], [-1, 0], [-1, 1], [0, -2], [-1, -2]],
  '2>3': [[0, 0], [1, 0], [1, 1], [0, -2], [1, -2]],
  '3>2': [[0, 0], [-1, 0], [-1, -1], [0, 2], [-1, 2]],
  '3>0': [[0, 0], [-1, 0], [-1, -1], [0, 2], [-1, 2]],
  '0>3': [[0, 0], [1, 0], [1, 1], [0, -2], [1, -2]],
};

const I_KICKS: Record<string, Array<[number, number]>> = {
  '0>1': [[0, 0], [-2, 0], [1, 0], [-2, -1], [1, 2]],
  '1>0': [[0, 0], [2, 0], [-1, 0], [2, 1], [-1, -2]],
  '1>2': [[0, 0], [-1, 0], [2, 0], [-1, 2], [2, -1]],
  '2>1': [[0, 0], [1, 0], [-2, 0], [1, -2], [-2, 1]],
  '2>3': [[0, 0], [2, 0], [-1, 0], [2, 1], [-1, -2]],
  '3>2': [[0, 0], [-2, 0], [1, 0], [-2, -1], [1, 2]],
  '3>0': [[0, 0], [1, 0], [-2, 0], [1, -2], [-2, 1]],
  '0>3': [[0, 0], [-1, 0], [2, 0], [-1, 2], [2, -1]],
};

export function pieceCells(piece: ActivePiece): Array<[number, number]> {
  const cells: Array<[number, number]> = [];
  ROTATIONS[piece.type][piece.rotation].forEach((row, y) => {
    row.forEach((filled, x) => {
      if (filled) cells.push([piece.x + x, piece.y + y]);
    });
  });
  return cells;
}

export function shapeOf(type: CellType): number[][] {
  return ROTATIONS[type][0];
}

function collides(state: GameState, piece: ActivePiece): boolean {
  return pieceCells(piece).some(([x, y]) => x < 0 || x >= BOARD_WIDTH || y >= BOARD_HEIGHT || (y >= 0 && state.board[y][x] !== null));
}

function emptyBoard(): Cell[][] {
  return Array.from({ length: BOARD_HEIGHT }, () => Array<Cell>(BOARD_WIDTH).fill(null));
}

function refillQueue(state: GameState): void {
  while (state.queue.length < 6) {
    if (state.bag.length === 0) {
      state.bag = [...PIECES];
      for (let index = state.bag.length - 1; index > 0; index--) {
        const swap = Math.floor(state.random() * (index + 1));
        [state.bag[index], state.bag[swap]] = [state.bag[swap], state.bag[index]];
      }
    }
    state.queue.push(state.bag.pop()!);
  }
}

function spawnPiece(state: GameState, type: CellType): boolean {
  const width = shapeOf(type)[0].length;
  const piece: ActivePiece = { type, rotation: 0, x: Math.floor((BOARD_WIDTH - width) / 2), y: type === 'I' ? -1 : 0 };
  if (collides(state, piece) && state.upgrades.shields > 0) {
    state.upgrades.shields -= 1;
    state.board.splice(BOARD_HEIGHT - 6, 6);
    state.board.unshift(...emptyBoard().slice(0, 6));
    state.events.push({ type: 'shield' });
  }
  if (collides(state, piece)) {
    state.active = null;
    state.over = true;
    state.events.push({ type: 'gameOver' });
    return false;
  }
  state.active = piece;
  state.lockTimer = 0;
  state.lockResets = 0;
  state.gravityAccumulator = 0;
  state.lastMoveWasRotation = false;
  return true;
}

function spawnNext(state: GameState): void {
  refillQueue(state);
  spawnPiece(state, state.queue.shift()!);
  refillQueue(state);
  state.holdUsed = false;
}

export function createGame(random: () => number = Math.random, mode: GameMode = 'arcade'): GameState {
  const state: GameState = {
    mode, won: false, energy: 0, missionLines: 0, missionTarget: 4, missions: 0,
    board: emptyBoard(),
    active: null,
    hold: null,
    holdUsed: false,
    queue: [],
    bag: [],
    score: 0,
    lines: 0,
    level: 1,
    combo: -1,
    backToBack: false,
    over: false,
    time: 0,
    feverUntil: 0,
    upgrades: { slowMo: 0, multiplier: 1, previews: 3, bombs: 0, lasers: 0, shields: 0 },
    upgradeChoices: null,
    events: [],
    gravityAccumulator: 0,
    lockTimer: 0,
    lockResets: 0,
    lastMoveWasRotation: false,
    bombArmed: false,
    random,
  };
  spawnNext(state);
  return state;
}

export function isPlayable(state: GameState): boolean {
  return !state.over && state.upgradeChoices === null && state.active !== null;
}

export function isFever(state: GameState): boolean {
  return state.time < state.feverUntil;
}

export function scoreMultiplier(state: GameState): number {
  return state.upgrades.multiplier * (isFever(state) ? 2 : 1);
}

function award(state: GameState, basePoints: number): number {
  const points = Math.round(basePoints * scoreMultiplier(state));
  state.score += points;
  return points;
}

export function gravityInterval(state: GameState): number {
  const base = Math.pow(Math.max(0.05, 0.8 - (state.level - 1) * 0.007), state.level - 1) * 1000;
  return Math.max(16, base * (1 + state.upgrades.slowMo * 0.2));
}

function onGround(state: GameState): boolean {
  return !!state.active && collides(state, { ...state.active, y: state.active.y + 1 });
}

function resetLockDelay(state: GameState): void {
  if (onGround(state) && state.lockResets < MAX_LOCK_RESETS) {
    state.lockTimer = 0;
    state.lockResets += 1;
  }
}

export function move(state: GameState, dx: number): boolean {
  if (!isPlayable(state)) return false;
  const next = { ...state.active!, x: state.active!.x + dx };
  if (collides(state, next)) return false;
  state.active = next;
  state.lastMoveWasRotation = false;
  resetLockDelay(state);
  return true;
}

export function rotate(state: GameState, direction: 1 | -1): boolean {
  if (!isPlayable(state)) return false;
  const piece = state.active!;
  if (piece.type === 'O' || piece.type === 'B') return false;
  const target = (piece.rotation + direction + 4) % 4;
  const kicks = (piece.type === 'I' ? I_KICKS : JLSTZ_KICKS)[`${piece.rotation}>${target}`];
  for (const [kickX, kickY] of kicks) {
    const candidate = { ...piece, rotation: target, x: piece.x + kickX, y: piece.y - kickY };
    if (!collides(state, candidate)) {
      state.active = candidate;
      state.lastMoveWasRotation = true;
      resetLockDelay(state);
      return true;
    }
  }
  return false;
}

export function ghostY(state: GameState): number {
  if (!state.active) return 0;
  let y = state.active.y;
  while (!collides(state, { ...state.active, y: y + 1 })) y += 1;
  return y;
}

function isTSpin(state: GameState): boolean {
  const piece = state.active;
  if (!piece || piece.type !== 'T' || !state.lastMoveWasRotation) return false;
  const corners: Array<[number, number]> = [[0, 0], [2, 0], [0, 2], [2, 2]];
  const blocked = corners.filter(([dx, dy]) => {
    const x = piece.x + dx;
    const y = piece.y + dy;
    return x < 0 || x >= BOARD_WIDTH || y >= BOARD_HEIGHT || (y >= 0 && state.board[y][x] !== null);
  });
  return blocked.length >= 3;
}

function removeRows(state: GameState, rows: number[]): void {
  const sorted = [...rows].sort((first, second) => second - first);
  for (const row of sorted) state.board.splice(row, 1);
  for (let index = 0; index < rows.length; index++) state.board.unshift(Array<Cell>(BOARD_WIDTH).fill(null));
}

export function activateOverdrive(state: GameState): boolean {
  if (!isPlayable(state) || state.energy < 100 || isFever(state)) return false;
  state.energy = 0;
  state.feverUntil = state.time + FEVER_DURATION_MS;
  state.events.push({ type: 'fever' });
  return true;
}
function finish(state: GameState): void {
  state.over = true;
  state.won = true;
  state.events.push({ type: 'gameOver' });
}
function registerLines(state: GameState, count: number): void {
  const previousLevel = state.level;
  state.lines += count;
  state.energy = Math.min(100, state.energy + count * 12 + Math.max(0, state.combo) * 4);
  state.missionLines += count;
  if (state.missionLines >= state.missionTarget) {
    state.missionLines -= state.missionTarget;
    state.missions += 1;
    const points = award(state, 500 * state.missions);
    state.upgrades.bombs += 1;
    state.missionTarget = Math.min(16, state.missionTarget + 2);
    state.events.push({ type: 'mission', points });
  }
  if (state.mode === 'sprint' && state.lines >= 40) {
    finish(state);
    return;
  }
  state.level = Math.floor(state.lines / LINES_PER_LEVEL) + 1;
  if (state.level > previousLevel) {
    state.events.push({ type: 'levelUp', level: state.level });
    offerUpgrades(state);
  }
}

function offerUpgrades(state: GameState): void {
  const pool = (Object.keys(UPGRADES) as UpgradeId[]).filter(id => id !== 'vision' || state.upgrades.previews < 5);
  for (let index = pool.length - 1; index > 0; index--) {
    const swap = Math.floor(state.random() * (index + 1));
    [pool[index], pool[swap]] = [pool[swap], pool[index]];
  }
  state.upgradeChoices = pool.slice(0, 3);
}

export function chooseUpgrade(state: GameState, id: UpgradeId): boolean {
  if (!state.upgradeChoices?.includes(id)) return false;
  if (id === 'slowMo') state.upgrades.slowMo += 1;
  if (id === 'multiplier') state.upgrades.multiplier = Math.round((state.upgrades.multiplier + 0.25) * 100) / 100;
  if (id === 'vision') state.upgrades.previews = Math.min(5, state.upgrades.previews + 1);
  if (id === 'bomb') state.upgrades.bombs += 2;
  if (id === 'laser') state.upgrades.lasers += 1;
  if (id === 'shield') state.upgrades.shields += 1;
  state.upgradeChoices = null;
  return true;
}

const CLEAR_LABELS = ['', 'SINGLE', 'DOUBLE', 'TRIPLE', 'TETRIS'];

function lockPiece(state: GameState): void {
  const piece = state.active!;
  const cells = pieceCells(piece);
  const tSpin = isTSpin(state);
  state.events.push({ type: 'lock', cells });

  if (cells.every(([, y]) => y < HIDDEN_ROWS)) {
    state.active = null;
    state.over = true;
    state.events.push({ type: 'gameOver' });
    return;
  }

  if (piece.type === 'B') {
    const [bombX, bombY] = cells[0];
    let cleared = 0;
    for (let y = bombY - 2; y <= bombY + 2; y++) {
      for (let x = bombX - 2; x <= bombX + 2; x++) {
        if (y >= 0 && y < BOARD_HEIGHT && x >= 0 && x < BOARD_WIDTH && state.board[y][x] !== null) {
          state.board[y][x] = null;
          cleared += 1;
        }
      }
    }
    const points = award(state, cleared * 25 * state.level);
    state.events.push({ type: 'explode', x: bombX, y: bombY, cleared, points });
  } else {
    for (const [x, y] of cells) {
      if (y >= 0) state.board[y][x] = piece.type;
    }
  }

  const fullRows = state.board.flatMap((row, y) => (row.every(cell => cell !== null) ? [y] : []));
  const count = fullRows.length;
  if (count > 0) {
    removeRows(state, fullRows);
    const difficult = count === 4 || tSpin;
    let base = tSpin ? [400, 800, 1200, 1600][count] : [0, 100, 300, 500, 800][count];
    base *= state.level;
    const backToBack = difficult && state.backToBack;
    if (backToBack) base *= 1.5;
    state.backToBack = difficult;
    state.combo += 1;
    if (state.combo > 0) base += 50 * state.combo * state.level;
    const perfect = state.board.every(row => row.every(cell => cell === null));
    if (perfect) base += 3000 * state.level;
    if (state.combo >= FEVER_COMBO - 1) {
      if (!isFever(state)) state.events.push({ type: 'fever' });
      state.feverUntil = state.time + FEVER_DURATION_MS;
    }
    const points = award(state, base);
    const label = perfect ? 'PERFECT CLEAR' : `${tSpin ? 'T-SPIN ' : ''}${CLEAR_LABELS[count]}`;
    state.events.push({ type: 'clear', rows: fullRows, count, label, points, tSpin, perfect, combo: state.combo, backToBack });
    registerLines(state, count);
  } else {
    state.combo = -1;
    if (tSpin) award(state, 400 * state.level);
  }

  state.active = null;
  if (!state.over) spawnNext(state);
}

export function softDrop(state: GameState): boolean {
  if (!isPlayable(state)) return false;
  const next = { ...state.active!, y: state.active!.y + 1 };
  if (collides(state, next)) return false;
  state.active = next;
  state.lastMoveWasRotation = false;
  award(state, 1);
  return true;
}

export function hardDrop(state: GameState): void {
  if (!isPlayable(state)) return;
  const target = ghostY(state);
  const distance = target - state.active!.y;
  if (distance > 0) state.lastMoveWasRotation = false;
  state.active = { ...state.active!, y: target };
  award(state, distance * 2);
  state.events.push({ type: 'hardDrop', piece: state.active.type, distance, cells: pieceCells(state.active) });
  lockPiece(state);
}

export function holdPiece(state: GameState): boolean {
  if (!isPlayable(state) || state.holdUsed || state.active!.type === 'B') return false;
  const current = state.active!.type as PieceType;
  if (state.hold) {
    const held = state.hold;
    state.hold = current;
    spawnPiece(state, held);
  } else {
    state.hold = current;
    state.active = null;
    refillQueue(state);
    spawnPiece(state, state.queue.shift()!);
    refillQueue(state);
  }
  state.holdUsed = true;
  return true;
}

export function useBomb(state: GameState): boolean {
  if (!isPlayable(state) || state.upgrades.bombs <= 0 || state.active!.type === 'B') return false;
  const current = state.active!;
  const bomb: ActivePiece = { type: 'B', rotation: 0, x: current.x + 1, y: Math.max(0, current.y) };
  if (collides(state, bomb)) return false;
  state.upgrades.bombs -= 1;
  state.queue.unshift(current.type as PieceType);
  state.active = bomb;
  state.lockTimer = 0;
  return true;
}

export function useLaser(state: GameState): boolean {
  if (!isPlayable(state) || state.upgrades.lasers <= 0) return false;
  state.upgrades.lasers -= 1;
  const rows = [BOARD_HEIGHT - 2, BOARD_HEIGHT - 1];
  const filled = rows.reduce((total, row) => total + state.board[row].filter(cell => cell !== null).length, 0);
  removeRows(state, rows);
  const points = award(state, filled * 30 * state.level);
  state.events.push({ type: 'laser', rows, points });
  while (state.active && collides(state, state.active)) state.active = { ...state.active, y: state.active.y - 1 };
  return true;
}

export function tick(state: GameState, deltaMs: number, softDropping = false): void {
  if (!isPlayable(state)) return;
  state.time += deltaMs;
  if (state.mode === 'blitz' && state.time >= BLITZ_DURATION) {
    state.time = BLITZ_DURATION;
    finish(state);
    return;
  }
  const interval = softDropping ? Math.min(gravityInterval(state), 33) : gravityInterval(state);
  state.gravityAccumulator += deltaMs;
  while (state.gravityAccumulator >= interval && state.active) {
    state.gravityAccumulator -= interval;
    if (softDropping ? !softDrop(state) : !moveDown(state)) {
      state.gravityAccumulator = 0;
      break;
    }
  }
  if (state.active && onGround(state)) {
    state.lockTimer += deltaMs;
    if (state.lockTimer >= LOCK_DELAY_MS) lockPiece(state);
  } else {
    state.lockTimer = 0;
  }
}

function moveDown(state: GameState): boolean {
  const next = { ...state.active!, y: state.active!.y + 1 };
  if (collides(state, next)) return false;
  state.active = next;
  state.lastMoveWasRotation = false;
  return true;
}

export function drainEvents(state: GameState): GameEvent[] {
  const events = state.events;
  state.events = [];
  return events;
}

// Blocage local de l'ecran de connexion. L'API repond le meme 401 generique pendant un blocage
// (rien ne dit pourquoi) : le navigateur compte lui-meme les refus pour afficher le compte a
// rebours et ne plus appeler le serveur. Memes seuils que auth, compteurs separes.

export type FailureKind = 'face' | 'password';

export interface LockoutState {
  face: number;
  password: number;
  windowStart: number;
  lockedUntil: number;
}

export const EMPTY_LOCKOUT: LockoutState = { face: 0, password: 0, windowStart: 0, lockedUntil: 0 };

export const LOCK_DURATION_MS = 5 * 60_000;
export const FAILURE_WINDOW_MS = 10 * 60_000;
const MAX_FAILURES: Record<FailureKind, number> = { face: 5, password: 3 };

export function remainingMs(state: LockoutState, now: number): number {
  return Math.max(0, state.lockedUntil - now);
}

export function isLocked(state: LockoutState, now: number): boolean {
  return remainingMs(state, now) > 0;
}

export function recordFailure(state: LockoutState, kind: FailureKind, now: number): LockoutState {
  if (isLocked(state, now)) return state;
  const fresh = now - state.windowStart > FAILURE_WINDOW_MS ? EMPTY_LOCKOUT : state;
  const next = {
    ...fresh,
    windowStart: fresh.windowStart || now,
    lockedUntil: 0,
    [kind]: fresh[kind] + 1,
  };
  if (next[kind] >= MAX_FAILURES[kind]) return { ...EMPTY_LOCKOUT, lockedUntil: now + LOCK_DURATION_MS };
  return next;
}

export function recordSuccess(_state: LockoutState): LockoutState {
  return EMPTY_LOCKOUT;
}

export function parseLockout(raw: string | null): LockoutState {
  if (!raw) return EMPTY_LOCKOUT;
  try {
    const value: unknown = JSON.parse(raw);
    if (typeof value !== 'object' || value === null) return EMPTY_LOCKOUT;
    const { face, password, windowStart, lockedUntil } = value as Record<string, unknown>;
    const all = [face, password, windowStart, lockedUntil];
    if (!all.every((n) => typeof n === 'number' && Number.isFinite(n) && n >= 0)) return EMPTY_LOCKOUT;
    return { face, password, windowStart, lockedUntil } as LockoutState;
  } catch {
    return EMPTY_LOCKOUT;
  }
}

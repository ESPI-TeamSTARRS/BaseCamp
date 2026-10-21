/**
 * Jeton d'acces garde UNIQUEMENT en memoire du module : jamais dans localStorage, sessionStorage
 * ni un cookie lisible par le script. Un rechargement complet de la page l'efface; la session est
 * alors retrouvee par le rafraichissement (cookie HttpOnly), voir `session-keeper.ts`.
 */
type Listener = () => void;

let accessToken: string | null = null;
let expiresAtMs = 0;
const listeners = new Set<Listener>();

function notify(): void {
  listeners.forEach((listener) => listener());
}

export function setSession(token: string, expiresInSeconds: number, nowMs: number = Date.now()): void {
  accessToken = token;
  expiresAtMs = nowMs + expiresInSeconds * 1000;
  notify();
}

/** Instant d'expiration du jeton d'acces en memoire, ou 0 sans session. */
export function getExpiresAtMs(): number {
  return accessToken === null ? 0 : expiresAtMs;
}

export function getAccessToken(nowMs: number = Date.now()): string | null {
  if (accessToken !== null && nowMs >= expiresAtMs) {
    clearSession();
  }
  return accessToken;
}

export function clearSession(): void {
  accessToken = null;
  expiresAtMs = 0;
  notify();
}

export function subscribeSession(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

import { refreshAccessToken, revokeRefreshToken } from './session-api';
import { clearSession, getExpiresAtMs, setSession, subscribeSession } from './session-store';

type FetchLike = typeof fetch;

const REFRESH_MARGIN_MS = 60_000;
const MIN_DELAY_MS = 5_000;
const RETRY_DELAY_MS = 30_000;
const MAX_RETRIES = 3;

export type RefreshOutcome = 'refreshed' | 'expired' | 'unavailable';

export type SessionKeeperDeps = {
  fetchImpl?: FetchLike;
  now?: () => number;
  setTimer?: (callback: () => void, delayMs: number) => unknown;
  clearTimer?: (handle: unknown) => void;
  /** Appelee quand une session ouverte ne peut plus etre rafraichie (a envoyer vers la connexion). */
  onExpired: () => void;
};

export type SessionKeeper = {
  /** Au chargement de la page : tente de retrouver la session grace au cookie de rafraichissement. */
  start: () => Promise<RefreshOutcome>;
  stop: () => void;
};

let inFlight: Promise<RefreshOutcome> | null = null;

/**
 * Un seul rafraichissement a la fois : deux appels simultanes partagent la meme requete. Sinon le
 * second presenterait un jeton deja consomme, ce que le serveur traite comme un rejeu et punit
 * en revoquant toute la session.
 */
export function refreshOnce(fetchImpl: FetchLike = fetch): Promise<RefreshOutcome> {
  if (inFlight) return inFlight;
  inFlight = (async (): Promise<RefreshOutcome> => {
    const result = await refreshAccessToken(fetchImpl);
    if (result.ok) {
      setSession(result.accessToken, result.expiresIn);
      return 'refreshed';
    }
    if (result.kind === 'expired') clearSession();
    return result.kind;
  })().finally(() => {
    inFlight = null;
  });
  return inFlight;
}

/** Deconnexion : revoque la session cote serveur (idempotent) puis efface le jeton en memoire. */
export async function signOut(fetchImpl: FetchLike = fetch): Promise<void> {
  await revokeRefreshToken(fetchImpl);
  clearSession();
}

/**
 * Rafraichit en silence avant l'expiration du jeton d'acces et au chargement de la page.
 * Un refus (401) arrete tout : pas de nouvelle tentative, donc pas de boucle de redirection.
 */
export function createSessionKeeper(deps: SessionKeeperDeps): SessionKeeper {
  const fetchImpl = deps.fetchImpl ?? fetch;
  const now = deps.now ?? Date.now;
  const setTimer = deps.setTimer ?? ((callback, delay) => setTimeout(callback, delay));
  const clearTimer = deps.clearTimer ?? ((handle) => clearTimeout(handle as ReturnType<typeof setTimeout>));
  let timer: unknown = null;
  let unsubscribe: (() => void) | null = null;
  let retries = 0;
  let stopped = false;

  function cancel(): void {
    if (timer !== null) clearTimer(timer);
    timer = null;
  }

  function schedule(delayMs: number, held: boolean): void {
    cancel();
    timer = setTimer(() => {
      timer = null;
      void attempt(held);
    }, delayMs);
  }

  function scheduleFromStore(): void {
    const expiresAt = getExpiresAtMs();
    if (stopped) return;
    if (expiresAt === 0) return cancel();
    retries = 0;
    schedule(Math.max(expiresAt - now() - REFRESH_MARGIN_MS, MIN_DELAY_MS), true);
  }

  async function attempt(held: boolean): Promise<RefreshOutcome> {
    const outcome = await refreshOnce(fetchImpl);
    if (stopped) return outcome;
    if (outcome === 'expired' && held) deps.onExpired();
    if (outcome === 'unavailable' && retries < MAX_RETRIES) {
      retries += 1;
      schedule(RETRY_DELAY_MS, held);
    }
    return outcome;
  }

  return {
    start: () => {
      stopped = false;
      unsubscribe = subscribeSession(scheduleFromStore);
      return attempt(false);
    },
    stop: () => {
      stopped = true;
      cancel();
      unsubscribe?.();
      unsubscribe = null;
    },
  };
}

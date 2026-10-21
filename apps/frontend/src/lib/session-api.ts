import { z } from 'zod';

type FetchLike = typeof fetch;

const REFRESH_URL = '/api/auth/refresh';
const LOGOUT_URL = '/api/auth/logout';
const REQUEST_TIMEOUT_MS = 10000;
const STATUS_OK = 200;
const STATUS_UNAUTHORIZED = 401;

// En-tete obligatoire cote serveur (anti-CSRF) : une page d'un autre site ne peut pas le poser.
const CSRF_HEADERS = { 'x-requested-with': 'basecamp-front' };

const RefreshBodySchema = z.object({
  access_token: z.string().min(1),
  expires_in: z.number().int().positive(),
});

export type RefreshResult =
  { ok: true; accessToken: string; expiresIn: number } | { ok: false; kind: 'expired' | 'unavailable' };

/**
 * Echange le cookie de rafraichissement (HttpOnly, jamais lu par le script) contre un nouveau jeton
 * d'acces. Jamais d'exception : un 401 veut dire « session finie », tout le reste « reessayez ».
 */
export async function refreshAccessToken(fetchImpl: FetchLike = fetch): Promise<RefreshResult> {
  try {
    const response = await fetchImpl(REFRESH_URL, {
      method: 'POST',
      headers: CSRF_HEADERS,
      credentials: 'same-origin',
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    if (response.status === STATUS_UNAUTHORIZED) return { ok: false, kind: 'expired' };
    if (response.status !== STATUS_OK) return { ok: false, kind: 'unavailable' };
    const parsed = RefreshBodySchema.safeParse(await response.json());
    if (!parsed.success) return { ok: false, kind: 'unavailable' };
    return { ok: true, accessToken: parsed.data.access_token, expiresIn: parsed.data.expires_in };
  } catch {
    return { ok: false, kind: 'unavailable' };
  }
}

/** Idempotent cote serveur : on ne distingue pas les issues, la session locale est de toute facon effacee. */
export async function revokeRefreshToken(fetchImpl: FetchLike = fetch): Promise<void> {
  try {
    await fetchImpl(LOGOUT_URL, {
      method: 'POST',
      headers: CSRF_HEADERS,
      credentials: 'same-origin',
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch {
    // Reseau coupe : le cookie expirera seul (7 jours) et le jeton d'acces en 15 minutes.
  }
}

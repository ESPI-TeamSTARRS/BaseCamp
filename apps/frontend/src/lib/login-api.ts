import { z } from 'zod';

type FetchLike = typeof fetch;

const LOGIN_URL = '/api/auth/login';
const REQUEST_TIMEOUT_MS = 10000;
const STATUS_OK = 200;
const STATUS_UNAUTHORIZED = 401;
const STATUS_UNPROCESSABLE = 422;
const STATUS_TOO_MANY = 429;

const LoginBodySchema = z.object({
  access_token: z.string().min(1),
  expires_in: z.number().int().positive(),
});

export type LoginResult =
  | { ok: true; accessToken: string; expiresIn: number }
  | { ok: false; kind: 'invalid_credentials' | 'invalid' | 'rate_limited' | 'unavailable' };

async function successResult(response: Response): Promise<LoginResult> {
  const parsed = LoginBodySchema.safeParse(await response.json());
  if (!parsed.success) return { ok: false, kind: 'unavailable' };
  return { ok: true, accessToken: parsed.data.access_token, expiresIn: parsed.data.expires_in };
}

/**
 * Jamais d'exception : aucun detail technique n'est remonte. Le cookie de rafraichissement est
 * HttpOnly : il est pose et renvoye par le navigateur, le script ne le voit jamais.
 */
export async function loginAccount(
  email: string,
  password: string,
  fetchImpl: FetchLike = fetch
): Promise<LoginResult> {
  try {
    const response = await fetchImpl(LOGIN_URL, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ email, password }),
      credentials: 'same-origin',
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    if (response.status === STATUS_OK) return await successResult(response);
    if (response.status === STATUS_UNAUTHORIZED) return { ok: false, kind: 'invalid_credentials' };
    if (response.status === STATUS_UNPROCESSABLE) return { ok: false, kind: 'invalid' };
    if (response.status === STATUS_TOO_MANY) return { ok: false, kind: 'rate_limited' };
    return { ok: false, kind: 'unavailable' };
  } catch {
    return { ok: false, kind: 'unavailable' };
  }
}

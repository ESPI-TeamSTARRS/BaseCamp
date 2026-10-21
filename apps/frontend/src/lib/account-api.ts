import { z } from 'zod';

type FetchLike = typeof fetch;

const REGISTER_URL = '/api/auth/register';
const VERIFY_URL = '/api/auth/verify-email';
const REQUEST_TIMEOUT_MS = 10000;
const STATUS_ACCEPTED = 202;
const STATUS_BAD_REQUEST = 400;
const STATUS_UNPROCESSABLE = 422;
const STATUS_TOO_MANY = 429;

const InvalidBodySchema = z.object({
  fields: z.array(z.string()).default([]),
  messages: z.array(z.string()).default([]),
});

export type RegisterResult =
  | { ok: true }
  | { ok: false; kind: 'invalid'; fields: string[]; messages: string[] }
  | { ok: false; kind: 'rate_limited' }
  | { ok: false; kind: 'unavailable' };

export type VerifyResult = { ok: true } | { ok: false; kind: 'invalid' | 'unavailable' };

function postJson(url: string, body: unknown, fetchImpl: FetchLike): Promise<Response> {
  return fetchImpl(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
    credentials: 'same-origin',
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });
}

async function invalidResult(response: Response): Promise<RegisterResult> {
  try {
    const body = InvalidBodySchema.parse(await response.json());
    return { ok: false, kind: 'invalid', fields: body.fields, messages: body.messages };
  } catch {
    return { ok: false, kind: 'unavailable' };
  }
}

/** Jamais d'exception : le detail technique n'est pas remonte, l'interface affiche un message generique. */
export async function registerAccount(
  email: string,
  password: string,
  fetchImpl: FetchLike = fetch
): Promise<RegisterResult> {
  try {
    const response = await postJson(REGISTER_URL, { email, password }, fetchImpl);
    if (response.status === STATUS_ACCEPTED) return { ok: true };
    if (response.status === STATUS_UNPROCESSABLE) return await invalidResult(response);
    if (response.status === STATUS_TOO_MANY) return { ok: false, kind: 'rate_limited' };
    return { ok: false, kind: 'unavailable' };
  } catch {
    return { ok: false, kind: 'unavailable' };
  }
}

export async function verifyEmailToken(token: string, fetchImpl: FetchLike = fetch): Promise<VerifyResult> {
  try {
    const response = await postJson(VERIFY_URL, { token }, fetchImpl);
    if (response.ok) return { ok: true };
    if (response.status === STATUS_BAD_REQUEST || response.status === STATUS_UNPROCESSABLE) {
      return { ok: false, kind: 'invalid' };
    }
    return { ok: false, kind: 'unavailable' };
  } catch {
    return { ok: false, kind: 'unavailable' };
  }
}

const FORGOT_URL = '/api/auth/password/forgot';
const RESET_URL = '/api/auth/password/reset';
const PASSWORD_REFUSED = 'Ce mot de passe est refusé.';

export type ForgotResult = { ok: true } | { ok: false; kind: 'rate_limited' | 'unavailable' };

export type ResetResult =
  | { ok: true }
  | { ok: false; kind: 'invalid_token' | 'rate_limited' | 'unavailable' }
  | { ok: false; kind: 'weak_password'; message: string };

/** Reponse neutre : le serveur repond 202 que le compte existe ou non, l'interface ne peut pas le deviner. */
export async function requestPasswordReset(
  email: string,
  fetchImpl: FetchLike = fetch
): Promise<ForgotResult> {
  try {
    const response = await postJson(FORGOT_URL, { email }, fetchImpl);
    if (response.status === STATUS_ACCEPTED) return { ok: true };
    if (response.status === STATUS_TOO_MANY) return { ok: false, kind: 'rate_limited' };
    return { ok: false, kind: 'unavailable' };
  } catch {
    return { ok: false, kind: 'unavailable' };
  }
}

async function unprocessableReset(response: Response): Promise<ResetResult> {
  try {
    const body = InvalidBodySchema.parse(await response.json());
    if (!body.fields.includes('password')) return { ok: false, kind: 'invalid_token' };
    return { ok: false, kind: 'weak_password', message: body.messages[0] ?? PASSWORD_REFUSED };
  } catch {
    return { ok: false, kind: 'unavailable' };
  }
}

/** Jamais d'exception : le detail technique n'est pas remonte, l'interface affiche un message generique. */
export async function resetPassword(
  token: string,
  password: string,
  fetchImpl: FetchLike = fetch
): Promise<ResetResult> {
  try {
    const response = await postJson(RESET_URL, { token, password }, fetchImpl);
    if (response.ok) return { ok: true };
    if (response.status === STATUS_BAD_REQUEST) return { ok: false, kind: 'invalid_token' };
    if (response.status === STATUS_UNPROCESSABLE) return await unprocessableReset(response);
    if (response.status === STATUS_TOO_MANY) return { ok: false, kind: 'rate_limited' };
    return { ok: false, kind: 'unavailable' };
  } catch {
    return { ok: false, kind: 'unavailable' };
  }
}

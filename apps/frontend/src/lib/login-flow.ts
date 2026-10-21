import { z } from 'zod';
import { loginAccount } from './login-api';
import { setSession } from './session-store';

type FetchLike = typeof fetch;

const MAX_PASSWORD = 128;

export type LoginFieldErrors = { email?: string; password?: string };
export type LoginInput = { email: string; password: string };

export type LoginValidation = { ok: true; values: LoginInput } | { ok: false; errors: LoginFieldErrors };

export type LoginState =
  | { status: 'success' }
  | { status: 'invalid'; errors: LoginFieldErrors }
  | { status: 'error'; message: string };

const EMAIL_INVALID = 'Saisissez une adresse email valide.';
const PASSWORD_REQUIRED = 'Saisissez votre mot de passe.';
const BAD_CREDENTIALS = 'Email ou mot de passe incorrect.';
const RATE_LIMITED = 'Trop de tentatives. Patientez une minute avant de réessayer.';
const UNAVAILABLE = 'Le service est momentanément indisponible. Réessayez dans quelques instants.';

const LoginSchema = z
  .object({
    email: z.string().trim().toLowerCase().max(254).email(EMAIL_INVALID),
    password: z.string().min(1, PASSWORD_REQUIRED).max(MAX_PASSWORD, PASSWORD_REQUIRED),
  })
  .strict();

/** Validation de confort : le serveur reste l'autorite et ne detaille jamais la cause d'un refus. */
export function validateLogin(input: LoginInput): LoginValidation {
  const parsed = LoginSchema.safeParse(input);
  if (parsed.success) return { ok: true, values: parsed.data };
  const errors: LoginFieldErrors = {};
  for (const issue of parsed.error.issues) {
    const field = issue.path[0];
    if ((field === 'email' || field === 'password') && !errors[field]) {
      errors[field] = field === 'email' ? EMAIL_INVALID : PASSWORD_REQUIRED;
    }
  }
  return { ok: false, errors };
}

function failure(kind: 'invalid_credentials' | 'invalid' | 'rate_limited' | 'unavailable'): LoginState {
  if (kind === 'invalid_credentials') return { status: 'error', message: BAD_CREDENTIALS };
  if (kind === 'rate_limited') return { status: 'error', message: RATE_LIMITED };
  return { status: 'error', message: UNAVAILABLE };
}

export async function submitLogin(input: LoginInput, fetchImpl: FetchLike = fetch): Promise<LoginState> {
  const checked = validateLogin(input);
  if (!checked.ok) return { status: 'invalid', errors: checked.errors };
  const result = await loginAccount(checked.values.email, checked.values.password, fetchImpl);
  if (!result.ok) return failure(result.kind);
  setSession(result.accessToken, result.expiresIn);
  return { status: 'success' };
}

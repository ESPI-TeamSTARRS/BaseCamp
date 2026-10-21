import { z } from 'zod';
import { registerAccount, verifyEmailToken } from './account-api';

type FetchLike = typeof fetch;

const MIN_PASSWORD = 12;
const MAX_PASSWORD = 128;
const TOKEN_FRAGMENT = /^#token=([A-Za-z0-9_-]{1,128})$/;

export type FieldErrors = { email?: string; password?: string };
export type RegistrationInput = { email: string; password: string };

export type ValidationResult = { ok: true; values: RegistrationInput } | { ok: false; errors: FieldErrors };

export type RegistrationState =
  | { status: 'success'; email: string }
  | { status: 'invalid'; errors: FieldErrors }
  | { status: 'error'; message: string };

export type VerificationState =
  { status: 'verified' } | { status: 'missing' } | { status: 'invalid' } | { status: 'unavailable' };

const RegistrationSchema = z
  .object({
    email: z.string().trim().toLowerCase().max(254).email('Saisissez une adresse email valide.'),
    password: z
      .string()
      .min(MIN_PASSWORD, `Le mot de passe doit contenir au moins ${MIN_PASSWORD} caractères.`)
      .max(MAX_PASSWORD, `Le mot de passe ne doit pas dépasser ${MAX_PASSWORD} caractères.`),
  })
  .strict();

const EMAIL_INVALID = 'Saisissez une adresse email valide.';
const GENERIC_FIELD_ERROR = 'Cette saisie est invalide.';
const RATE_LIMITED = 'Trop de tentatives. Patientez une minute avant de réessayer.';
const UNAVAILABLE = 'Le service est momentanément indisponible. Réessayez dans quelques instants.';

/** Validation de confort cote client : le serveur reste l'autorite (12 caracteres, mots de passe courants refuses). */
export function validateRegistration(input: RegistrationInput): ValidationResult {
  const parsed = RegistrationSchema.safeParse(input);
  if (parsed.success) return { ok: true, values: parsed.data };
  const errors: FieldErrors = {};
  for (const issue of parsed.error.issues) {
    const field = issue.path[0];
    if ((field === 'email' || field === 'password') && !errors[field]) {
      errors[field] = issue.message === 'Invalid email' ? EMAIL_INVALID : issue.message;
    }
  }
  return { ok: false, errors };
}

function serverErrors(fields: string[], messages: string[]): FieldErrors {
  const errors: FieldErrors = {};
  fields.forEach((field, index) => {
    if (field === 'email' || field === 'password') errors[field] = messages[index] ?? GENERIC_FIELD_ERROR;
  });
  return errors;
}

export async function submitRegistration(
  input: RegistrationInput,
  fetchImpl: FetchLike = fetch
): Promise<RegistrationState> {
  const checked = validateRegistration(input);
  if (!checked.ok) return { status: 'invalid', errors: checked.errors };
  const result = await registerAccount(checked.values.email, checked.values.password, fetchImpl);
  if (result.ok) return { status: 'success', email: checked.values.email };
  if (result.kind === 'invalid')
    return { status: 'invalid', errors: serverErrors(result.fields, result.messages) };
  return { status: 'error', message: result.kind === 'rate_limited' ? RATE_LIMITED : UNAVAILABLE };
}

/** Le jeton voyage dans le fragment de l'URL : il n'atteint ni les journaux d'acces ni le Referer. */
export function readVerificationToken(hash: string): string | null {
  return TOKEN_FRAGMENT.exec(hash)?.[1] ?? null;
}

export async function verifyFromHash(hash: string, fetchImpl: FetchLike = fetch): Promise<VerificationState> {
  const token = readVerificationToken(hash);
  if (!token) return { status: 'missing' };
  const result = await verifyEmailToken(token, fetchImpl);
  if (result.ok) return { status: 'verified' };
  return { status: result.kind };
}

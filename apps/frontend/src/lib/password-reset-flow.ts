import { z } from 'zod';
import { requestPasswordReset, resetPassword } from './account-api';
import { readVerificationToken } from './registration-flow';

type FetchLike = typeof fetch;

const MIN_PASSWORD = 12;
const MAX_PASSWORD = 128;

const EMAIL_INVALID = 'Saisissez une adresse email valide.';
const RATE_LIMITED = 'Trop de tentatives. Patientez une minute avant de réessayer.';
const UNAVAILABLE = 'Le service est momentanément indisponible. Réessayez dans quelques instants.';
const MISMATCH = 'Les deux mots de passe ne correspondent pas.';

export type ForgotState =
  | { status: 'success'; email: string }
  | { status: 'invalid'; message: string }
  | { status: 'error'; message: string };

export type ResetFieldErrors = { password?: string; confirmation?: string };

export type ResetState =
  | { status: 'success' }
  | { status: 'missing' }
  | { status: 'invalid_token' }
  | { status: 'invalid'; errors: ResetFieldErrors }
  | { status: 'error'; message: string };

export type ResetInput = { hash: string; password: string; confirmation: string };

const EmailSchema = z.string().trim().toLowerCase().max(254).email(EMAIL_INVALID);

const PasswordSchema = z
  .string()
  .min(MIN_PASSWORD, `Le mot de passe doit contenir au moins ${MIN_PASSWORD} caractères.`)
  .max(MAX_PASSWORD, `Le mot de passe ne doit pas dépasser ${MAX_PASSWORD} caractères.`);

function failureMessage(kind: 'rate_limited' | 'unavailable'): string {
  return kind === 'rate_limited' ? RATE_LIMITED : UNAVAILABLE;
}

/** Le message de succes est le meme que le compte existe ou non (le serveur repond toujours 202). */
export async function submitForgotPassword(
  email: string,
  fetchImpl: FetchLike = fetch
): Promise<ForgotState> {
  const parsed = EmailSchema.safeParse(email);
  if (!parsed.success) return { status: 'invalid', message: EMAIL_INVALID };
  const result = await requestPasswordReset(parsed.data, fetchImpl);
  if (result.ok) return { status: 'success', email: parsed.data };
  return { status: 'error', message: failureMessage(result.kind) };
}

/** Meme format de fragment que la verification d'email : le jeton n'atteint ni les journaux ni le Referer. */
export function readResetToken(hash: string): string | null {
  return readVerificationToken(hash);
}

/** Validation de confort cote client : le serveur reste l'autorite (mots de passe courants refuses). */
export function validateNewPassword(
  password: string,
  confirmation: string
): { ok: true } | { ok: false; errors: ResetFieldErrors } {
  const parsed = PasswordSchema.safeParse(password);
  if (!parsed.success) return { ok: false, errors: { password: parsed.error.issues[0].message } };
  if (password !== confirmation) return { ok: false, errors: { confirmation: MISMATCH } };
  return { ok: true };
}

export async function submitPasswordReset(
  input: ResetInput,
  fetchImpl: FetchLike = fetch
): Promise<ResetState> {
  const token = readResetToken(input.hash);
  if (!token) return { status: 'missing' };
  const checked = validateNewPassword(input.password, input.confirmation);
  if (!checked.ok) return { status: 'invalid', errors: checked.errors };
  const result = await resetPassword(token, input.password, fetchImpl);
  if (result.ok) return { status: 'success' };
  if (result.kind === 'invalid_token') return { status: 'invalid_token' };
  if (result.kind === 'weak_password') return { status: 'invalid', errors: { password: result.message } };
  return { status: 'error', message: failureMessage(result.kind) };
}

'use client';

import Link from 'next/link';
import { useState, type FormEvent } from 'react';
import { MailCheck } from 'lucide-react';
import { submitForgotPassword, type ForgotState } from '../lib/password-reset-flow';
import { FieldError, FormError, inputClass, submitClass } from './FormField';

export function ForgotPasswordForm() {
  const [pending, setPending] = useState(false);
  const [state, setState] = useState<ForgotState | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setPending(true);
    setState(await submitForgotPassword(String(data.get('email') ?? '')));
    setPending(false);
  }

  if (state?.status === 'success') {
    return (
      <div role="status" className="rounded-card bg-white p-6 text-center shadow-card">
        <MailCheck className="mx-auto text-forest" size={40} />
        <h2 className="mt-4 text-xl font-bold text-forest-deep">Vérifiez votre boîte mail</h2>
        <p className="mt-2 text-granite/80">
          Si un compte existe pour <strong>{state.email}</strong>, un email contenant un lien de
          réinitialisation vient d&apos;être envoyé. Le lien est valable 30 minutes.
        </p>
      </div>
    );
  }

  const invalid = state?.status === 'invalid' ? state.message : undefined;
  return (
    <form onSubmit={onSubmit} noValidate className="rounded-card bg-white p-6 shadow-card">
      <label htmlFor="email" className="block text-sm font-medium text-granite">
        Adresse email
        <input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          required
          maxLength={254}
          aria-invalid={Boolean(invalid)}
          aria-describedby={invalid ? 'email-error' : undefined}
          className={inputClass}
        />
      </label>
      <FieldError id="email-error" message={invalid} />
      {state?.status === 'error' && <FormError message={state.message} />}
      <button type="submit" disabled={pending} className={submitClass}>
        {pending ? 'Envoi en cours…' : 'Recevoir un lien'}
      </button>
      <p className="mt-6 text-center text-sm text-granite/70">
        <Link href="/compte/inscription" className="text-forest underline">
          Créer mon compte
        </Link>
      </p>
    </form>
  );
}

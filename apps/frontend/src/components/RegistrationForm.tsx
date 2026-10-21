'use client';

import Link from 'next/link';
import { useState, type FormEvent } from 'react';
import { MailCheck } from 'lucide-react';
import { submitRegistration, type FieldErrors, type RegistrationState } from '../lib/registration-flow';

const inputClass =
  'mt-2 block h-12 w-full rounded-lg border border-granite/20 bg-white px-4 text-base text-granite focus:border-forest focus:outline-none focus:ring-2 focus:ring-forest/30';

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} role="alert" className="mt-2 text-sm text-bivouac-dark">
      {message}
    </p>
  );
}

export function RegistrationForm() {
  const [pending, setPending] = useState(false);
  const [state, setState] = useState<RegistrationState | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setPending(true);
    setState(
      await submitRegistration({
        email: String(data.get('email') ?? ''),
        password: String(data.get('password') ?? ''),
      })
    );
    setPending(false);
  }

  if (state?.status === 'success') {
    return (
      <div role="status" className="rounded-card bg-white p-6 text-center shadow-card">
        <MailCheck className="mx-auto text-forest" size={40} />
        <h2 className="mt-4 text-xl font-bold text-forest-deep">Vérifiez votre boîte mail</h2>
        <p className="mt-2 text-granite/80">
          Si cette adresse peut être inscrite, un email de confirmation vient d&apos;être envoyé à{' '}
          <strong>{state.email}</strong>. Le lien est valable 24 heures.
        </p>
      </div>
    );
  }

  const errors: FieldErrors = state?.status === 'invalid' ? state.errors : {};
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
          aria-invalid={Boolean(errors.email)}
          aria-describedby={errors.email ? 'email-error' : undefined}
          className={inputClass}
        />
      </label>
      <FieldError id="email-error" message={errors.email} />

      <label htmlFor="password" className="mt-6 block text-sm font-medium text-granite">
        Mot de passe
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="new-password"
          required
          maxLength={128}
          aria-invalid={Boolean(errors.password)}
          aria-describedby={errors.password ? 'password-error' : 'password-help'}
          className={inputClass}
        />
      </label>
      <p id="password-help" className="mt-2 text-sm text-granite/70">
        12 caractères minimum. Aucune règle de composition : une phrase longue convient très bien.
      </p>
      <FieldError id="password-error" message={errors.password} />

      {state?.status === 'error' && (
        <p role="alert" className="mt-6 rounded-lg bg-bivouac/10 p-3 text-sm text-bivouac-dark">
          {state.message}
        </p>
      )}

      <button
        type="submit"
        disabled={pending}
        className="mt-6 h-12 w-full rounded-lg bg-bivouac text-base font-bold text-white transition-colors hover:bg-bivouac-dark disabled:opacity-60"
      >
        {pending ? 'Création en cours…' : 'Créer mon compte'}
      </button>
      <p className="mt-6 text-center text-sm text-granite/70">
        En créant un compte, vous acceptez nos{' '}
        <Link href="/cgv" className="text-forest underline">
          conditions générales de vente
        </Link>
        .
      </p>
    </form>
  );
}

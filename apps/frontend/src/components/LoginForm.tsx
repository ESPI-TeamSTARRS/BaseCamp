'use client';

import Link from 'next/link';
import { useState, type FormEvent } from 'react';
import { CheckCircle2 } from 'lucide-react';
import { submitLogin, type LoginFieldErrors, type LoginState } from '../lib/login-flow';

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

export function LoginForm() {
  const [pending, setPending] = useState(false);
  const [state, setState] = useState<LoginState | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setPending(true);
    setState(
      await submitLogin({
        email: String(data.get('email') ?? ''),
        password: String(data.get('password') ?? ''),
      })
    );
    setPending(false);
  }

  if (state?.status === 'success') {
    return (
      <div role="status" className="rounded-card bg-white p-6 text-center shadow-card">
        <CheckCircle2 className="mx-auto text-forest" size={40} />
        <h2 className="mt-4 text-xl font-bold text-forest-deep">Vous êtes connecté</h2>
        <p className="mt-2 text-granite/80">Content de vous revoir. Votre prochain bivouac vous attend.</p>
        <Link
          href="/"
          className="mt-6 inline-flex h-12 items-center rounded-lg bg-bivouac px-6 font-bold text-white hover:bg-bivouac-dark"
        >
          Découvrir le catalogue
        </Link>
      </div>
    );
  }

  const errors: LoginFieldErrors = state?.status === 'invalid' ? state.errors : {};
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
          autoComplete="current-password"
          required
          maxLength={128}
          aria-invalid={Boolean(errors.password)}
          aria-describedby={errors.password ? 'password-error' : undefined}
          className={inputClass}
        />
      </label>
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
        {pending ? 'Connexion en cours…' : 'Me connecter'}
      </button>
      <p className="mt-6 text-center text-sm text-granite/70">
        Pas encore de compte ?{' '}
        <Link href="/compte/inscription" className="text-forest underline">
          Créer mon compte
        </Link>
      </p>
    </form>
  );
}

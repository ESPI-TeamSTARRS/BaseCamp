'use client';

import Link from 'next/link';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { CheckCircle2, XCircle } from 'lucide-react';
import { readResetToken, submitPasswordReset, type ResetState } from '../lib/password-reset-flow';
import { FieldError, FormError, inputClass, submitClass } from './FormField';

const LINK_PROBLEMS = {
  missing: "Ce lien est incomplet. Ouvrez-le depuis l'email reçu.",
  invalid_token: 'Ce lien de réinitialisation est invalide, expiré ou déjà utilisé.',
} as const;

export function ResetPasswordForm() {
  // Le jeton quitte la barre d'adresse avant tout appel : ni historique, ni Referer, ni journal d'acces.
  const hash = useRef<string | null>(null);
  const [hasToken, setHasToken] = useState<boolean | null>(null);
  const [pending, setPending] = useState(false);
  const [state, setState] = useState<ResetState | null>(null);

  useEffect(() => {
    hash.current = window.location.hash;
    window.history.replaceState(null, '', window.location.pathname);
    setHasToken(readResetToken(hash.current) !== null);
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setPending(true);
    setState(
      await submitPasswordReset({
        hash: hash.current ?? '',
        password: String(data.get('password') ?? ''),
        confirmation: String(data.get('confirmation') ?? ''),
      })
    );
    setPending(false);
  }

  if (hasToken === null) return null;
  if (state?.status === 'success') {
    return (
      <div role="status" className="rounded-card bg-white p-6 text-center shadow-card">
        <CheckCircle2 className="mx-auto text-forest" size={40} />
        <h2 className="mt-4 text-xl font-bold text-forest-deep">Mot de passe modifié</h2>
        <p className="mt-2 text-granite/80">
          Vos sessions ont été fermées. Un email de confirmation vous a été envoyé.
        </p>
      </div>
    );
  }
  const problem = !hasToken ? 'missing' : state?.status === 'invalid_token' ? 'invalid_token' : null;
  if (problem) {
    return (
      <div role="alert" className="rounded-card bg-white p-6 text-center shadow-card">
        <XCircle className="mx-auto text-bivouac" size={40} />
        <h2 className="mt-4 text-xl font-bold text-forest-deep">Réinitialisation impossible</h2>
        <p className="mt-2 text-granite/80">{LINK_PROBLEMS[problem]}</p>
        <Link href="/compte/mot-de-passe-oublie" className="mt-6 inline-block text-forest underline">
          Demander un nouveau lien
        </Link>
      </div>
    );
  }

  const errors = state?.status === 'invalid' ? state.errors : {};
  return (
    <form onSubmit={onSubmit} noValidate className="rounded-card bg-white p-6 shadow-card">
      <label htmlFor="password" className="block text-sm font-medium text-granite">
        Nouveau mot de passe
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

      <label htmlFor="confirmation" className="mt-6 block text-sm font-medium text-granite">
        Confirmer le mot de passe
        <input
          id="confirmation"
          name="confirmation"
          type="password"
          autoComplete="new-password"
          required
          maxLength={128}
          aria-invalid={Boolean(errors.confirmation)}
          aria-describedby={errors.confirmation ? 'confirmation-error' : undefined}
          className={inputClass}
        />
      </label>
      <FieldError id="confirmation-error" message={errors.confirmation} />

      {state?.status === 'error' && <FormError message={state.message} />}
      <button type="submit" disabled={pending} className={submitClass}>
        {pending ? 'Enregistrement…' : 'Enregistrer le mot de passe'}
      </button>
    </form>
  );
}

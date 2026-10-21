'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { CheckCircle2, Loader2, XCircle } from 'lucide-react';
import { verifyFromHash, type VerificationState } from '../lib/registration-flow';

const MESSAGES: Record<Exclude<VerificationState['status'], 'verified'>, string> = {
  missing: "Ce lien est incomplet. Ouvrez-le depuis l'email reçu.",
  invalid: 'Ce lien de vérification est invalide, expiré ou déjà utilisé.',
  unavailable: 'Le service est momentanément indisponible. Réessayez dans quelques instants.',
};

export function EmailVerification() {
  const [state, setState] = useState<VerificationState | null>(null);

  useEffect(() => {
    let active = true;
    const hash = window.location.hash;
    // Le jeton quitte la barre d'adresse avant tout appel : il ne reste ni dans l'historique ni dans un Referer.
    window.history.replaceState(null, '', window.location.pathname);
    void verifyFromHash(hash).then((result) => {
      if (active) setState(result);
    });
    return () => {
      active = false;
    };
  }, []);

  if (state === null) {
    return (
      <p role="status" className="flex items-center justify-center gap-2 text-granite/80">
        <Loader2 className="animate-spin" size={20} /> Vérification en cours…
      </p>
    );
  }
  if (state.status === 'verified') {
    return (
      <div role="status" className="rounded-card bg-white p-6 text-center shadow-card">
        <CheckCircle2 className="mx-auto text-forest" size={40} />
        <h2 className="mt-4 text-xl font-bold text-forest-deep">Adresse confirmée</h2>
        <p className="mt-2 text-granite/80">Merci, votre adresse email est vérifiée.</p>
        <Link
          href="/"
          className="mt-6 inline-flex h-12 items-center rounded-lg bg-bivouac px-6 font-bold text-white hover:bg-bivouac-dark"
        >
          Découvrir le catalogue
        </Link>
      </div>
    );
  }
  return (
    <div role="alert" className="rounded-card bg-white p-6 text-center shadow-card">
      <XCircle className="mx-auto text-bivouac" size={40} />
      <h2 className="mt-4 text-xl font-bold text-forest-deep">Confirmation impossible</h2>
      <p className="mt-2 text-granite/80">{MESSAGES[state.status]}</p>
      <Link href="/compte/inscription" className="mt-6 inline-block text-forest underline">
        Retour à l&apos;inscription
      </Link>
    </div>
  );
}

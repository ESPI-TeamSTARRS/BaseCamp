'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import { useCart } from '../context/CartContext';
import {
  confirmPayment,
  loadPaymentView,
  PAYMENT_UNAVAILABLE_MESSAGE as UNAVAILABLE,
  requestPayment,
  type PaymentRequest,
  type TestPaymentMethod,
} from '../lib/order-payment';

type View =
  | { step: 'loading' }
  | { step: 'ready'; payment: PaymentRequest; declined: boolean }
  | { step: 'paying'; payment: PaymentRequest }
  | { step: 'error'; message: string; retry: boolean };

/** Écran de paiement simulé : aucun champ de carte, seulement un résultat de test à choisir. */
export function PaymentScreen({ orderId }: { orderId: string }) {
  const router = useRouter();
  const { clearCart } = useCart();
  const [view, setView] = useState<View>({ step: 'loading' });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void loadPaymentView(orderId).then((next) => {
      if (!cancelled) setView(next);
    });
    return () => {
      cancelled = true;
    };
  }, [orderId, attempt]);

  async function pay(payment: PaymentRequest, method: TestPaymentMethod) {
    setView({ step: 'paying', payment });
    const result = await confirmPayment(orderId, method);
    if (!result.ok) {
      const message = result.reason === 'not_payable' ? result.message : UNAVAILABLE;
      setView({ step: 'error', message, retry: result.reason === 'unavailable' });
      return;
    }
    if (result.result.paymentStatus === 'succeeded') {
      clearCart();
      router.push(`/success?commande=${encodeURIComponent(result.result.orderNumber)}`);
      return;
    }
    // Refus de test : l'intention est terminale, on en redemande une nouvelle pour le nouvel essai.
    const next = await requestPayment(orderId);
    if (next.ok) setView({ step: 'ready', payment: next.payment, declined: true });
    else setView({ step: 'error', message: UNAVAILABLE, retry: true });
  }

  return (
    <section className="mx-auto max-w-lg px-4 py-12">
      <h1 className="flex items-center gap-2 text-2xl font-bold text-granite">
        <ShieldCheck className="text-forest" /> Paiement
      </h1>
      <p className="mt-2 text-sm text-granite/70">
        Paiement de démonstration : aucune donnée bancaire n&apos;est demandée.
      </p>

      {view.step === 'loading' && <p className="mt-8 text-granite/70">Préparation du paiement…</p>}

      {view.step === 'error' && (
        <div role="alert" className="mt-8 space-y-4">
          <p className="text-red-700">{view.message}</p>
          {view.retry ? (
            <button
              type="button"
              onClick={() => {
                setView({ step: 'loading' });
                setAttempt((n) => n + 1);
              }}
              className="rounded-full bg-forest px-6 py-3 text-sm font-semibold text-sand hover:bg-forest-light"
            >
              Réessayer
            </button>
          ) : (
            <Link href="/" className="inline-block text-sm font-medium text-forest underline">
              Retour à la boutique
            </Link>
          )}
        </div>
      )}

      {(view.step === 'ready' || view.step === 'paying') && (
        <div className="mt-8 space-y-6">
          <dl className="rounded-2xl bg-sand p-5 text-sm">
            <div className="flex justify-between">
              <dt className="text-granite/70">Commande</dt>
              <dd className="font-semibold text-granite">{view.payment.orderNumber}</dd>
            </div>
            <div className="mt-2 flex justify-between text-base font-bold text-granite">
              <dt>Montant à payer</dt>
              <dd>{view.payment.amountEur.toFixed(2)} €</dd>
            </div>
          </dl>

          {view.step === 'ready' && view.declined && (
            <p role="alert" className="text-sm text-red-700">
              Paiement refusé. Vous pouvez réessayer.
            </p>
          )}

          <div className="grid gap-3">
            <button
              type="button"
              disabled={view.step === 'paying'}
              onClick={() => pay(view.payment, 'pm_test_success')}
              className="rounded-full bg-bivouac py-3.5 text-base font-semibold text-white hover:bg-bivouac-dark disabled:opacity-60"
            >
              {view.step === 'paying' ? 'Paiement en cours…' : 'Simuler un paiement réussi'}
            </button>
            <button
              type="button"
              disabled={view.step === 'paying'}
              onClick={() => pay(view.payment, 'pm_test_declined')}
              className="rounded-full border border-granite/30 py-3.5 text-base font-semibold text-granite hover:bg-granite/5 disabled:opacity-60"
            >
              Simuler un refus de paiement
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

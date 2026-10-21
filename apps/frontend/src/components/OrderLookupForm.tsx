'use client';

import { useState, type FormEvent } from 'react';
import { lookupOrder, type TrackedOrder } from '../lib/order-lookup';

type View =
  | { step: 'form' }
  | { step: 'searching' }
  | { step: 'found'; order: TrackedOrder }
  | { step: 'message'; text: string };

const NOT_FOUND = 'Aucune commande ne correspond à ces informations. Vérifiez le numéro et l’email saisis.';
const INVALID = 'Le numéro (BC- suivi de 10 caractères) ou l’email n’a pas le bon format.';
const UNAVAILABLE = 'Le suivi est momentanément indisponible. Réessayez dans un instant.';

const inputClass =
  'mt-1 w-full rounded-lg border border-granite/20 bg-white px-3 py-2.5 text-sm text-granite focus:border-forest focus:outline-none focus:ring-2 focus:ring-forest/30';

const euros = (value: number) => `${value.toFixed(2)} €`;

export function OrderLookupForm() {
  const [orderNumber, setOrderNumber] = useState('');
  const [email, setEmail] = useState('');
  const [view, setView] = useState<View>({ step: 'form' });

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setView({ step: 'searching' });
    const result = await lookupOrder(orderNumber, email);
    if (result.ok) setView({ step: 'found', order: result.order });
    else if (result.reason === 'invalid') setView({ step: 'message', text: INVALID });
    else if (result.reason === 'not_found') setView({ step: 'message', text: NOT_FOUND });
    else setView({ step: 'message', text: UNAVAILABLE });
  }

  return (
    <div className="mt-8 space-y-6">
      <form onSubmit={handleSubmit} noValidate className="space-y-4 rounded-2xl bg-sand p-5">
        <label className="block text-sm font-medium text-granite">
          Numéro de commande
          <input
            value={orderNumber}
            onChange={(event) => setOrderNumber(event.target.value)}
            placeholder="BC-XXXXXXXXXX"
            autoComplete="off"
            className={inputClass}
          />
        </label>
        <label className="block text-sm font-medium text-granite">
          Email utilisé pour la commande
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
            className={inputClass}
          />
        </label>
        <button
          type="submit"
          disabled={view.step === 'searching'}
          className="w-full rounded-full bg-bivouac py-3 text-base font-semibold text-white hover:bg-bivouac-dark disabled:opacity-60"
        >
          {view.step === 'searching' ? 'Recherche…' : 'Suivre ma commande'}
        </button>
      </form>

      {view.step === 'message' && (
        <p role="alert" className="text-sm text-red-700">
          {view.text}
        </p>
      )}

      {view.step === 'found' && (
        <section aria-label="Commande" className="space-y-4 rounded-2xl border border-granite/10 p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-granite">{view.order.number}</h2>
            <span className="rounded-full bg-forest/10 px-3 py-1 text-sm font-medium text-forest">
              {view.order.statusLabel}
            </span>
          </div>
          <ul className="divide-y divide-granite/10 text-sm">
            {view.order.lines.map((line) => (
              <li key={line.name} className="flex justify-between py-2">
                <span>
                  {line.name} × {line.quantity}
                </span>
                <span>{euros(line.lineTotalEur)}</span>
              </li>
            ))}
          </ul>
          <dl className="space-y-1 text-sm text-granite/70">
            <div className="flex justify-between">
              <dt>Sous-total</dt>
              <dd>{euros(view.order.subtotalEur)}</dd>
            </div>
            <div className="flex justify-between">
              <dt>Livraison</dt>
              <dd>{view.order.shippingEur === 0 ? 'Offerte' : euros(view.order.shippingEur)}</dd>
            </div>
            <div className="flex justify-between text-base font-bold text-granite">
              <dt>Total</dt>
              <dd>{euros(view.order.totalEur)}</dd>
            </div>
          </dl>
        </section>
      )}
    </div>
  );
}

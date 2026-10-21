'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { loadRecap, type RecapResult } from '../lib/order-recap';

const eur = (value: number) =>
  new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' }).format(value);

/** Récapitulatif réel de la commande (lignes et total lus côté serveur, jamais recalculés ici). */
export function OrderRecap({ number }: { number: string }) {
  const [recap, setRecap] = useState<RecapResult | null>(null);

  useEffect(() => {
    let cancelled = false;
    void loadRecap(number, window.sessionStorage).then((result) => {
      if (!cancelled) setRecap(result);
    });
    return () => {
      cancelled = true;
    };
  }, [number]);

  if (recap === null) return <p className="text-granite/70">Chargement du récapitulatif…</p>;
  if (recap.kind === 'unavailable')
    return (
      <p className="text-granite/70">
        Le récapitulatif est momentanément indisponible. Votre commande est bien enregistrée.
      </p>
    );
  if (recap.kind === 'no_email')
    return (
      <p className="text-granite/70">
        Retrouvez le détail de votre commande depuis la page{' '}
        <Link href="/suivi" className="font-semibold text-forest underline">
          Suivi de commande
        </Link>
        .
      </p>
    );

  const { order } = recap;
  return (
    <div
      className="w-full rounded-2xl border border-granite/10 bg-white p-6 text-left"
      data-testid="order-recap"
    >
      <p className="text-sm font-semibold text-forest">{order.statusLabel}</p>
      <ul className="mt-4 divide-y divide-granite/10">
        {order.lines.map((line) => (
          <li key={line.name} className="flex justify-between gap-4 py-2 text-sm text-granite">
            <span>
              {line.quantity} × {line.name}
            </span>
            <span>{eur(line.lineTotalEur)}</span>
          </li>
        ))}
      </ul>
      <dl className="mt-4 space-y-1 text-sm text-granite/80">
        <div className="flex justify-between">
          <dt>Sous-total</dt>
          <dd>{eur(order.subtotalEur)}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Livraison</dt>
          <dd>{eur(order.shippingEur)}</dd>
        </div>
        <div className="flex justify-between text-base font-bold text-granite">
          <dt>Total</dt>
          <dd data-testid="order-total">{eur(order.totalEur)}</dd>
        </div>
      </dl>
    </div>
  );
}

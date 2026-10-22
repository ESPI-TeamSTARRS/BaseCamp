'use client';

import Link from 'next/link';

import { useEffect, useState } from 'react';
import { formatEuros } from '@/lib/catalog/money';
import { ordersApi } from '@/lib/orders/api';
import { formatDateTime, statusLabel } from '@/lib/orders/format';
import type { OrderDetail } from '@/lib/orders/types';

type State =
  | { status: 'loading' }
  | { status: 'error'; code: string; detail: string }
  | { status: 'ready'; order: OrderDetail };

const BACK = (
  <p>
    <Link href="/commandes">← Retour aux commandes</Link>
  </p>
);

/** Detail d'une commande en lecture seule : aucune action, aucun champ modifiable. */
export function OrderDetailView({ orderId }: { orderId: string }) {
  const [attempt, setAttempt] = useState(0);
  const [settled, setSettled] = useState<{
    key: string;
    value: Exclude<State, { status: 'loading' }>;
  } | null>(null);
  const key = `${orderId}|${attempt}`;
  const state: State = settled?.key === key ? settled.value : { status: 'loading' };

  useEffect(() => {
    let current = true;
    void (async () => {
      const result = await ordersApi.get(orderId);
      if (current)
        setSettled({
          key,
          value: result.ok
            ? { status: 'ready', order: result.data }
            : { status: 'error', code: result.code, detail: result.detail },
        });
    })();
    return () => {
      current = false;
    };
  }, [key, orderId]);

  if (state.status === 'loading')
    return (
      <>
        {BACK}
        <p role="status" aria-busy="true">
          Chargement de la commande…
        </p>
      </>
    );
  if (state.status === 'error')
    return (
      <>
        {BACK}
        <div role="alert" className="alert">
          <p>{state.detail}</p>
          {state.code !== 'not_found' && (
            <button type="button" className="button secondary" onClick={() => setAttempt((n) => n + 1)}>
              Réessayer
            </button>
          )}
        </div>
      </>
    );
  const { order } = state;
  const address = order.shipping_address;
  return (
    <>
      {BACK}
      <h2>Commande {order.number}</h2>
      <p>
        <span className="badge">{statusLabel(order.status)}</span>
      </p>
      <dl>
        <dt>Passée le</dt>
        <dd>{formatDateTime(order.created_at)}</dd>
        <dt>Client</dt>
        <dd>{order.email}</dd>
      </dl>
      <div className="table-wrap">
        <table>
          <caption>Articles de la commande</caption>
          <thead>
            <tr>
              <th scope="col">Article</th>
              <th scope="col">Prix unitaire</th>
              <th scope="col">Quantité</th>
              <th scope="col">Total</th>
            </tr>
          </thead>
          <tbody>
            {order.lines.map((line, index) => (
              <tr key={`${line.name}-${index}`}>
                <td>{line.name}</td>
                <td>{formatEuros(line.unit_price_cents)}</td>
                <td>{line.quantity}</td>
                <td>{formatEuros(line.line_total_cents)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <section aria-label="Totaux">
        <dl>
          <dt>Sous-total</dt>
          <dd>{formatEuros(order.subtotal_cents)}</dd>
          <dt>Livraison</dt>
          <dd>{formatEuros(order.shipping_cents)}</dd>
          <dt>
            <strong>Total</strong>
          </dt>
          <dd>
            <strong>{formatEuros(order.total_cents)}</strong>
          </dd>
        </dl>
      </section>
      <section aria-label="Adresse de livraison">
        <h3>Adresse de livraison</h3>
        <address>
          {address.full_name}
          <br />
          {address.line1}
          <br />
          {address.line2 && (
            <>
              {address.line2}
              <br />
            </>
          )}
          {address.postal_code} {address.city}
          <br />
          {address.country}
        </address>
      </section>
    </>
  );
}

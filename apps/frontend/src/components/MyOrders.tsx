'use client';

import Link from 'next/link';
import { useEffect, useState, useSyncExternalStore } from 'react';
import { fetchMyOrders, type MyOrder } from '../lib/my-orders';
import { refreshOnce } from '../lib/session-keeper';
import { getAccessToken, subscribeSession } from '../lib/session-store';

type View =
  | { step: 'loading' }
  | { step: 'anonymous' }
  | { step: 'error' }
  | { step: 'loaded'; orders: MyOrder[]; total: number };

const euros = (value: number) => `${value.toFixed(2)} €`;
const dateFormat = new Intl.DateTimeFormat('fr-FR', { dateStyle: 'long' });

function OrderCard({ order }: { order: MyOrder }) {
  return (
    <li className="space-y-3 rounded-2xl border border-granite/10 bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-granite">{order.number}</h2>
          <p className="text-sm text-granite/60">{dateFormat.format(new Date(order.createdAt))}</p>
        </div>
        <span className="rounded-full bg-forest/10 px-3 py-1 text-sm font-medium text-forest">
          {order.statusLabel}
        </span>
      </div>
      <ul className="divide-y divide-granite/10 text-sm">
        {order.lines.map((line) => (
          <li key={line.name} className="flex justify-between py-2">
            <span>
              {line.name} × {line.quantity}
            </span>
            <span>{euros(line.lineTotalEur)}</span>
          </li>
        ))}
      </ul>
      <p className="flex justify-between text-base font-bold text-granite">
        <span>Total</span>
        <span>{euros(order.totalEur)}</span>
      </p>
    </li>
  );
}

export function MyOrders() {
  const signedIn = useSyncExternalStore(
    subscribeSession,
    () => getAccessToken() !== null,
    () => false
  );
  const [view, setView] = useState<View>({ step: 'loading' });

  useEffect(() => {
    let cancelled = false;

    async function load() {
      let token = getAccessToken();
      if (token === null) {
        // Rechargement de la page : le jeton d'accès (en mémoire) est perdu, le cookie de
        // rafraîchissement le rend. Sans cookie valide, le visiteur reste anonyme.
        if ((await refreshOnce()) !== 'refreshed') return !cancelled && setView({ step: 'anonymous' });
        token = getAccessToken();
      }
      if (token === null) return !cancelled && setView({ step: 'anonymous' });
      let result = await fetchMyOrders(token);
      if (!result.ok && result.reason === 'unauthenticated') {
        // Jeton refusé : une seule tentative après rafraîchissement, jamais de boucle.
        const outcome = await refreshOnce();
        token = outcome === 'refreshed' ? getAccessToken() : null;
        result = token ? await fetchMyOrders(token) : result;
      }
      if (cancelled) return;
      if (result.ok) setView({ step: 'loaded', orders: result.orders, total: result.total });
      else setView({ step: result.reason === 'unauthenticated' ? 'anonymous' : 'error' });
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [signedIn]);

  if (view.step === 'loading') {
    return (
      <p role="status" className="text-granite/70">
        Chargement de vos commandes…
      </p>
    );
  }
  if (view.step === 'anonymous') {
    return (
      <div role="status" className="rounded-2xl bg-sand p-6">
        <p className="text-granite">Connectez-vous pour retrouver vos commandes.</p>
        <Link
          href="/compte/connexion"
          className="mt-4 inline-flex h-11 items-center rounded-lg bg-bivouac px-5 font-bold text-white hover:bg-bivouac-dark"
        >
          Me connecter
        </Link>
        <p className="mt-4 text-sm text-granite/70">
          Vous avez commandé sans compte ?{' '}
          <Link href="/suivi" className="underline">
            Suivez votre commande avec son numéro
          </Link>
          .
        </p>
      </div>
    );
  }
  if (view.step === 'error') {
    return (
      <p role="alert" className="text-sm text-red-700">
        Vos commandes sont momentanément indisponibles. Réessayez dans un instant.
      </p>
    );
  }
  if (view.orders.length === 0) {
    return (
      <div className="rounded-2xl bg-sand p-6 text-granite">
        <p>Vous n’avez pas encore de commande.</p>
        <Link href="/" className="mt-3 inline-block underline">
          Découvrir le catalogue
        </Link>
      </div>
    );
  }
  return (
    <ul aria-label="Mes commandes" className="space-y-4">
      {view.orders.map((order) => (
        <OrderCard key={order.id} order={order} />
      ))}
    </ul>
  );
}

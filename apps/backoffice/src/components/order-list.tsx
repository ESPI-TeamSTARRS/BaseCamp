'use client';

import Link from 'next/link';

import { useEffect, useState, type FormEvent } from 'react';
import { formatEuros } from '@/lib/catalog/money';
import { ordersApi } from '@/lib/orders/api';
import { formatDateTime, STATUS_LABELS, statusLabel } from '@/lib/orders/format';
import type { OrderPage } from '@/lib/orders/types';

const PAGE_SIZE = 20;

type State =
  { status: 'loading' } | { status: 'error'; detail: string } | { status: 'ready'; page: OrderPage };

export function OrderList() {
  const [draft, setDraft] = useState('');
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [settled, setSettled] = useState<{
    key: string;
    value: Exclude<State, { status: 'loading' }>;
  } | null>(null);
  const key = [query, status, offset, attempt].join('|');
  const state: State = settled?.key === key ? settled.value : { status: 'loading' };

  useEffect(() => {
    let current = true;
    void (async () => {
      const result = await ordersApi.list({ q: query, status, offset, limit: PAGE_SIZE });
      if (current)
        setSettled({
          key,
          value: result.ok
            ? { status: 'ready', page: result.data }
            : { status: 'error', detail: result.detail },
        });
    })();
    return () => {
      current = false;
    };
  }, [key, query, status, offset]);

  function search(event: FormEvent) {
    event.preventDefault();
    setOffset(0);
    setQuery(draft);
  }

  function reset() {
    setDraft('');
    setQuery('');
    setStatus('');
    setOffset(0);
  }

  return (
    <>
      <div className="toolbar">
        <form role="search" onSubmit={search} className="toolbar">
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="order-search">Rechercher par numéro ou e-mail</label>
            <input
              id="order-search"
              type="search"
              value={draft}
              maxLength={100}
              onChange={(event) => setDraft(event.target.value)}
            />
          </div>
          <button type="submit" className="button">
            Rechercher
          </button>
        </form>
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor="order-status">Statut</label>
          <select
            id="order-status"
            value={status}
            onChange={(event) => {
              setOffset(0);
              setStatus(event.target.value);
            }}
          >
            <option value="">Tous les statuts</option>
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <Body
        state={state}
        filtered={query.trim() !== '' || status !== ''}
        offset={offset}
        onRetry={() => setAttempt((n) => n + 1)}
        onReset={reset}
        onPage={setOffset}
      />
    </>
  );
}

function Body(props: {
  state: State;
  filtered: boolean;
  offset: number;
  onRetry: () => void;
  onReset: () => void;
  onPage: (offset: number) => void;
}) {
  const { state, offset } = props;
  if (state.status === 'loading')
    return (
      <p role="status" aria-busy="true">
        Chargement des commandes…
      </p>
    );
  if (state.status === 'error')
    return (
      <div role="alert" className="alert">
        <p>{state.detail}</p>
        <button type="button" className="button secondary" onClick={props.onRetry}>
          Réessayer
        </button>
      </div>
    );
  const { items, total } = state.page;
  if (total === 0)
    return props.filtered ? (
      <div role="status">
        <p>Aucune commande ne correspond à ces critères.</p>
        <button type="button" className="button secondary" onClick={props.onReset}>
          Effacer les filtres
        </button>
      </div>
    ) : (
      <p role="status">Aucune commande pour le moment.</p>
    );
  const first = offset + 1;
  const last = offset + items.length;
  return (
    <>
      <p role="status">
        Commandes {first} à {last} sur {total}
      </p>
      <div className="table-wrap">
        <table>
          <caption>Commandes clients</caption>
          <thead>
            <tr>
              <th scope="col">Numéro</th>
              <th scope="col">Date</th>
              <th scope="col">Client</th>
              <th scope="col">Articles</th>
              <th scope="col">Total</th>
              <th scope="col">Statut</th>
            </tr>
          </thead>
          <tbody>
            {items.map((order) => (
              <tr key={order.id}>
                <td>
                  <Link href={`/commandes/${encodeURIComponent(order.id)}`}>{order.number}</Link>
                </td>
                <td>{formatDateTime(order.created_at)}</td>
                <td>{order.email}</td>
                <td>{order.item_count}</td>
                <td>{formatEuros(order.total_cents)}</td>
                <td>
                  <span className="badge">{statusLabel(order.status)}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <nav className="pager" aria-label="Pagination">
        <button
          type="button"
          className="button secondary"
          disabled={offset === 0}
          onClick={() => props.onPage(Math.max(0, offset - PAGE_SIZE))}
        >
          Page précédente
        </button>
        <button
          type="button"
          className="button secondary"
          disabled={offset + PAGE_SIZE >= total}
          onClick={() => props.onPage(offset + PAGE_SIZE)}
        >
          Page suivante
        </button>
      </nav>
    </>
  );
}

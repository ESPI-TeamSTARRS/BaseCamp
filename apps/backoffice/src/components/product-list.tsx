'use client';

import Link from 'next/link';

import { useEffect, useState, type FormEvent } from 'react';
import { catalogApi } from '@/lib/catalog/api';
import { formatEuros } from '@/lib/catalog/money';
import { AVAILABILITY_LABELS, categoryLabel, type ProductPage } from '@/lib/catalog/types';

const PAGE_SIZE = 20;

type State =
  { status: 'loading' } | { status: 'error'; detail: string } | { status: 'ready'; page: ProductPage };

export function ProductList() {
  const [draft, setDraft] = useState('');
  const [query, setQuery] = useState('');
  const [archived, setArchived] = useState(false);
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [settled, setSettled] = useState<{
    key: string;
    value: Exclude<State, { status: 'loading' }>;
  } | null>(null);
  const key = [query, archived, offset, attempt].join('|');
  const state: State = settled?.key === key ? settled.value : { status: 'loading' };

  useEffect(() => {
    let current = true;
    void (async () => {
      const result = await catalogApi.list({ q: query, includeArchived: archived, offset, limit: PAGE_SIZE });
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
  }, [key, query, archived, offset]);
  function search(event: FormEvent) {
    event.preventDefault();
    setOffset(0);
    setQuery(draft);
  }

  function reset() {
    setDraft('');
    setQuery('');
    setOffset(0);
  }

  return (
    <>
      <div className="toolbar">
        <form role="search" onSubmit={search} className="toolbar">
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="catalog-search">Rechercher un produit par nom</label>
            <input
              id="catalog-search"
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
        <label>
          <input
            type="checkbox"
            checked={archived}
            onChange={(event) => {
              setOffset(0);
              setArchived(event.target.checked);
            }}
          />{' '}
          Afficher les produits archivés
        </label>
        <Link className="button secondary" href="/produits/nouveau">
          Nouveau produit
        </Link>
      </div>
      <Body
        state={state}
        query={query}
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
  query: string;
  offset: number;
  onRetry: () => void;
  onReset: () => void;
  onPage: (offset: number) => void;
}) {
  const { state, query, offset } = props;
  if (state.status === 'loading')
    return (
      <p role="status" aria-busy="true">
        Chargement du catalogue…
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
    return query.trim() ? (
      <div role="status">
        <p>Aucun produit ne correspond à « {query.trim()} ».</p>
        <button type="button" className="button secondary" onClick={props.onReset}>
          Effacer la recherche
        </button>
      </div>
    ) : (
      <p role="status">
        Le catalogue est vide. <Link href="/produits/nouveau">Créer le premier produit</Link>.
      </p>
    );
  const first = offset + 1;
  const last = offset + items.length;
  return (
    <>
      <p role="status">
        Produits {first} à {last} sur {total}
      </p>
      <div className="table-wrap">
        <table>
          <caption>Produits du catalogue</caption>
          <thead>
            <tr>
              <th scope="col">Image</th>
              <th scope="col">Nom</th>
              <th scope="col">Catégorie</th>
              <th scope="col">Prix</th>
              <th scope="col">Stock</th>
              <th scope="col">État</th>
            </tr>
          </thead>
          <tbody>
            {items.map((product) => (
              <tr key={product.id}>
                <td>
                  {product.image_urls[0] ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img className="thumb" src={product.image_urls[0]} alt="" />
                  ) : (
                    <span
                      className="thumb"
                      style={{ display: 'inline-block' }}
                      role="img"
                      aria-label="Aucune image"
                    />
                  )}
                </td>
                <td>
                  <Link href={`/produits/${encodeURIComponent(product.id)}`}>{product.name}</Link>
                </td>
                <td>{categoryLabel(product.category)}</td>
                <td>{formatEuros(product.price_cents)}</td>
                <td>{product.stock}</td>
                <td>
                  <span className="badge">
                    {product.archived_at
                      ? 'Archivé'
                      : (AVAILABILITY_LABELS[product.availability] ?? product.availability)}
                  </span>
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

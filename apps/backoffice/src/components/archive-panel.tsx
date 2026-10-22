'use client';

import { useEffect, useRef, useState } from 'react';
import { catalogApi } from '@/lib/catalog/api';
import type { Product } from '@/lib/catalog/types';

/** Archivage avec confirmation explicite : le produit disparait du site client, sans suppression. */
export function ArchivePanel({
  product,
  onArchived,
}: {
  product: Product;
  onArchived: (product: Product) => void;
}) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const cancel = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (asking) cancel.current?.focus();
  }, [asking]);

  async function confirm() {
    setBusy(true);
    const result = await catalogApi.archive(product.id);
    setBusy(false);
    if (result.ok) onArchived(result.data);
    else setProblem(result.detail);
  }

  if (!asking)
    return (
      <p>
        <button type="button" className="button danger" onClick={() => setAsking(true)}>
          Archiver ce produit
        </button>
      </p>
    );
  return (
    <div role="alertdialog" aria-labelledby="archive-title" aria-describedby="archive-text" className="alert">
      <h2 id="archive-title">Archiver « {product.name} » ?</h2>
      <p id="archive-text">
        Le produit disparaîtra du site client et ne pourra plus être modifié. Il restera visible dans le
        back-office avec le filtre « Afficher les produits archivés ».
      </p>
      {problem && <p role="alert">{problem}</p>}
      <button type="button" className="button danger" onClick={confirm} disabled={busy}>
        {busy ? 'Archivage…' : 'Confirmer l’archivage'}
      </button>{' '}
      <button
        ref={cancel}
        type="button"
        className="button secondary"
        onClick={() => setAsking(false)}
        disabled={busy}
      >
        Annuler
      </button>
    </div>
  );
}

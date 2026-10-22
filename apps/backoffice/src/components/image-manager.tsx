'use client';

import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import { catalogApi } from '@/lib/catalog/api';
import { IMAGE_RULE, imageProblem } from '@/lib/catalog/image-check';
import type { Product } from '@/lib/catalog/types';

const MAX_IMAGES = 10;

/** Images du produit : galerie actuelle, apercu avant envoi, refus explicite (format, poids, serveur). */
export function ImageManager({
  product,
  onUpdated,
}: {
  product: Product;
  onUpdated: (product: Product) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview);
    },
    [preview]
  );

  function clear() {
    setFile(null);
    setPreview(null);
    if (input.current) input.current.value = '';
  }

  function choose(event: ChangeEvent<HTMLInputElement>) {
    const chosen = event.target.files?.[0] ?? null;
    setSent(false);
    clear();
    if (!chosen) {
      setProblem(null);
      return;
    }
    const refusal = imageProblem(chosen);
    setProblem(refusal);
    if (refusal === null) {
      setFile(chosen);
      setPreview(URL.createObjectURL(chosen));
    } else if (input.current) {
      input.current.value = '';
    }
  }

  async function send() {
    if (!file) return;
    setSending(true);
    setProblem(null);
    const result = await catalogApi.uploadImage(product.id, file);
    setSending(false);
    if (result.ok) {
      clear();
      setSent(true);
      onUpdated(result.data);
    } else {
      setProblem(result.detail);
    }
  }

  const full = product.image_urls.length >= MAX_IMAGES;
  return (
    <section aria-labelledby="images-title">
      <h2 id="images-title">Images</h2>
      {product.image_urls.length === 0 ? (
        <p>Aucune image pour le moment.</p>
      ) : (
        <ul className="gallery">
          {product.image_urls.map((url, index) => (
            <li key={url}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={url} alt={`Image ${index + 1} de ${product.name}`} />
            </li>
          ))}
        </ul>
      )}
      {full ? (
        <p>Le nombre maximal d’images ({MAX_IMAGES}) est atteint.</p>
      ) : (
        <div className="field">
          <label htmlFor="image-file">Ajouter une image</label>
          <input
            ref={input}
            id="image-file"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={choose}
            aria-describedby="image-rule"
          />
          <span id="image-rule" className="hint">
            {IMAGE_RULE}
          </span>
        </div>
      )}
      {problem && (
        <p role="alert" className="alert">
          {problem}
        </p>
      )}
      {preview && (
        <div>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img className="preview" src={preview} alt="Aperçu de l’image à envoyer" />
          <p>
            <button type="button" className="button" onClick={send} disabled={sending}>
              {sending ? 'Envoi en cours…' : 'Envoyer l’image'}
            </button>{' '}
            <button type="button" className="button secondary" onClick={clear} disabled={sending}>
              Annuler
            </button>
          </p>
        </div>
      )}
      {sent && (
        <p role="status" className="notice">
          Image ajoutée.
        </p>
      )}
    </section>
  );
}

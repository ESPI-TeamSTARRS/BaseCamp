'use client';

import Link from 'next/link';

import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { ArchivePanel } from '@/components/archive-panel';
import { Field } from '@/components/field';
import { ImageManager } from '@/components/image-manager';
import { catalogApi } from '@/lib/catalog/api';
import {
  EMPTY_VALUES,
  toCreatePayload,
  toUpdatePayload,
  validateForm,
  valuesFromProduct,
  type FieldErrors,
  type FormValues,
} from '@/lib/catalog/form-values';
import { CATEGORIES, type Product } from '@/lib/catalog/types';

type Load = 'loading' | 'ready' | 'missing' | 'failed';

const ORDER: Array<keyof FormValues> = [
  'name',
  'slug',
  'category',
  'price',
  'comparePrice',
  'stock',
  'shortDescription',
  'description',
  'weightGrams',
  'waterproofingMm',
  'comfortTempC',
  'seasons',
  'capacityLiters',
  'material',
];

export function ProductForm({ productId }: { productId?: string }) {
  const editing = productId !== undefined;
  const [load, setLoad] = useState<Load>(editing ? 'loading' : 'ready');
  const [loadError, setLoadError] = useState('');
  const [product, setProduct] = useState<Product | null>(null);
  const [values, setValues] = useState<FormValues>(EMPTY_VALUES);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [created, setCreated] = useState<Product | null>(null);
  const summary = useRef<HTMLDivElement>(null);

  const applyLoaded = useCallback((result: Awaited<ReturnType<typeof catalogApi.get>>) => {
    if (result.ok) {
      setProduct(result.data);
      setValues(valuesFromProduct(result.data));
      setLoad('ready');
    } else {
      setLoadError(result.detail);
      setLoad(result.status === 404 ? 'missing' : 'failed');
    }
  }, []);

  const reload = useCallback(async () => {
    if (productId === undefined) return;
    setLoad('loading');
    applyLoaded(await catalogApi.get(productId));
  }, [productId, applyLoaded]);

  useEffect(() => {
    if (productId === undefined) return;
    let current = true;
    void (async () => {
      const result = await catalogApi.get(productId);
      if (current) applyLoaded(result);
    })();
    return () => {
      current = false;
    };
  }, [productId, applyLoaded]);
  function set(field: keyof FormValues, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    setNotice(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setProblem(null);
    setNotice(null);
    const found = validateForm(values, editing ? 'edit' : 'create');
    setErrors(found);
    const firstInvalid = ORDER.find((field) => found[field]);
    if (firstInvalid) {
      document.getElementById(`pf-${firstInvalid}`)?.focus();
      return;
    }
    setSaving(true);
    const result =
      editing && product
        ? await catalogApi.update(product.id, toUpdatePayload(values, product.version))
        : await catalogApi.create(toCreatePayload(values));
    setSaving(false);
    if (result.ok) {
      if (editing) {
        setProduct(result.data);
        setValues(valuesFromProduct(result.data));
        setConflict(false);
        setNotice('Modifications enregistrées.');
      } else {
        setCreated(result.data);
      }
      return;
    }
    if (result.code === 'stale_version') setConflict(true);
    else if (result.code === 'duplicate') setErrors({ slug: result.detail });
    else setProblem(result.detail);
    summary.current?.focus();
  }

  if (created)
    return (
      <div role="status" className="notice">
        <p>Produit « {created.name} » créé.</p>
        <p>
          <Link className="button" href={`/produits/${encodeURIComponent(created.id)}`}>
            Ajouter des images
          </Link>{' '}
          <Link className="button secondary" href="/produits">
            Retour au catalogue
          </Link>
        </p>
      </div>
    );
  if (load === 'loading')
    return (
      <p role="status" aria-busy="true">
        Chargement du produit…
      </p>
    );
  if (load === 'missing')
    return (
      <div role="alert" className="alert">
        <p>{loadError}</p>
        <Link href="/produits">Retour au catalogue</Link>
      </div>
    );
  if (load === 'failed')
    return (
      <div role="alert" className="alert">
        <p>{loadError}</p>
        <button type="button" className="button secondary" onClick={() => void reload()}>
          Réessayer
        </button>
      </div>
    );

  const archived = product?.archived_at != null;
  const errorCount = Object.values(errors).filter(Boolean).length;
  const text = (
    field: keyof FormValues,
    label: string,
    extra: { hint?: string; max?: number; type?: string; inputMode?: 'numeric' | 'decimal' } = {}
  ) => (
    <Field id={`pf-${field}`} label={label} hint={extra.hint} error={errors[field]}>
      {(describedBy) => (
        <input
          id={`pf-${field}`}
          type={extra.type ?? 'text'}
          inputMode={extra.inputMode}
          value={values[field]}
          maxLength={extra.max}
          onChange={(event) => set(field, event.target.value)}
          aria-invalid={errors[field] ? true : undefined}
          aria-describedby={describedBy}
        />
      )}
    </Field>
  );

  return (
    <>
      <p>
        <Link href="/produits">← Retour au catalogue</Link>
      </p>
      <div ref={summary} tabIndex={-1}>
        {archived && (
          <p role="status" className="alert">
            Ce produit est archivé : il n’est plus visible sur le site et ne peut plus être modifié.
          </p>
        )}
        {errorCount > 0 && (
          <p role="alert" className="alert">
            Corrigez {errorCount} champ{errorCount > 1 ? 's' : ''} avant d’enregistrer.
          </p>
        )}
        {problem && (
          <p role="alert" className="alert">
            {problem}
          </p>
        )}
        {conflict && (
          <div role="alert" className="alert">
            <p>
              Ce produit a été modifié ailleurs depuis son ouverture. Vos modifications n’ont pas été
              enregistrées.
            </p>
            <button
              type="button"
              className="button"
              onClick={() => void reload().then(() => setConflict(false))}
            >
              Recharger la dernière version
            </button>
          </div>
        )}
        {notice && (
          <p role="status" className="notice">
            {notice}
          </p>
        )}
      </div>
      <form onSubmit={submit} noValidate aria-label={editing ? 'Modifier le produit' : 'Nouveau produit'}>
        <fieldset disabled={archived || saving}>
          <legend>Informations</legend>
          {text('name', 'Nom', { max: 200 })}
          {!editing &&
            text('slug', 'Identifiant (facultatif)', {
              hint: 'Minuscules, chiffres et tirets. Déduit du nom s’il est vide.',
              max: 128,
            })}
          <Field id="pf-category" label="Catégorie" error={errors.category}>
            {(describedBy) => (
              <select
                id="pf-category"
                value={values.category}
                onChange={(event) => set('category', event.target.value)}
                aria-invalid={errors.category ? true : undefined}
                aria-describedby={describedBy}
              >
                <option value="">Choisir…</option>
                {CATEGORIES.map((category) => (
                  <option key={category.value} value={category.value}>
                    {category.label}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <div className="grid">
            {text('price', 'Prix (€)', { inputMode: 'decimal', hint: 'Ex. 129,90' })}
            {text('comparePrice', 'Prix barré (€, facultatif)', { inputMode: 'decimal' })}
            {text('stock', 'Stock', { inputMode: 'numeric' })}
          </div>
          {text('shortDescription', 'Description courte', { max: 300 })}
          <Field id="pf-description" label="Description" error={errors.description}>
            {(describedBy) => (
              <textarea
                id="pf-description"
                rows={6}
                value={values.description}
                maxLength={5000}
                onChange={(event) => set('description', event.target.value)}
                aria-invalid={errors.description ? true : undefined}
                aria-describedby={describedBy}
              />
            )}
          </Field>
        </fieldset>
        <fieldset disabled={archived || saving}>
          <legend>Caractéristiques techniques (facultatives)</legend>
          <div className="grid">
            {text('weightGrams', 'Poids (g)', { inputMode: 'numeric' })}
            {text('waterproofingMm', 'Imperméabilité (mm)', { inputMode: 'numeric' })}
            {text('comfortTempC', 'Température de confort (°C)', { inputMode: 'numeric' })}
            {text('seasons', 'Saisons (0 à 4)', { inputMode: 'numeric' })}
            {text('capacityLiters', 'Capacité (L)', { inputMode: 'numeric' })}
            {text('material', 'Matériau', { max: 100 })}
          </div>
        </fieldset>
        {!archived && (
          <button type="submit" className="button" disabled={saving}>
            {saving ? 'Enregistrement…' : editing ? 'Enregistrer les modifications' : 'Créer le produit'}
          </button>
        )}
      </form>
      {editing && product && !archived && (
        <>
          <ImageManager product={product} onUpdated={(updated) => setProduct(updated)} />
          <ArchivePanel
            product={product}
            onArchived={(updated) => {
              setProduct(updated);
              setNotice('Produit archivé.');
            }}
          />
        </>
      )}
      {editing && product && archived && product.image_urls.length > 0 && (
        <ul className="gallery">
          {product.image_urls.map((url, index) => (
            <li key={url}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={url} alt={`Image ${index + 1} de ${product.name}`} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

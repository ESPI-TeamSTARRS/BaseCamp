'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useRef, useState, type ChangeEvent, type FormEvent } from 'react';
import { Minus, Plus } from 'lucide-react';
import { useCart } from '../context/CartContext';
import {
  SHIPPING_COUNTRIES,
  validateOrderForm,
  type OrderForm,
  type OrderFormErrors,
} from '../lib/order-form';
import { IdempotencyKeys, placeOrder } from '../lib/place-order';

type Phase = 'idle' | 'submitting' | 'redirecting';

const EMPTY_FORM: OrderForm = {
  email: '',
  fullName: '',
  line1: '',
  line2: '',
  postalCode: '',
  city: '',
  country: 'FR',
};

const STOCK_MESSAGE =
  "Un article n'est plus disponible en quantité suffisante. Ajustez les quantités signalées puis réessayez.";
const UNAVAILABLE_MESSAGE =
  'Le service de commande est momentanément indisponible. Réessayez dans un instant.';
const PAYMENT_MESSAGE =
  "Votre commande est enregistrée, mais l'étape de paiement n'a pas pu démarrer. Cliquez de nouveau pour réessayer : aucune commande en double ne sera créée.";

const inputClass =
  'w-full rounded-lg border border-granite/20 bg-white px-3 py-2.5 text-sm text-granite focus:border-forest focus:outline-none focus:ring-2 focus:ring-forest/30';

async function startPayment(lines: { productId: string; quantity: number }[]): Promise<string | null> {
  try {
    const response = await fetch('/api/checkout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lines }),
    });
    const data: { url?: string } = await response.json();
    return typeof data.url === 'string' ? data.url : null;
  } catch {
    return null;
  }
}

export function CartPage() {
  const { lines, items, quote, quoteStatus, setQuantity, removeItem } = useCart();
  const [form, setForm] = useState<OrderForm>(EMPTY_FORM);
  const [errors, setErrors] = useState<OrderFormErrors>({});
  const [phase, setPhase] = useState<Phase>('idle');
  const [message, setMessage] = useState<string | null>(null);
  const keys = useRef(new IdempotencyKeys());

  const quoteByProduct = new Map((quote?.lines ?? []).map((line) => [line.productId, line]));
  const busy = phase !== 'idle';
  const canOrder = quoteStatus === 'ready' && quote !== null && !quote.hasIssues && !busy;

  function update(field: keyof OrderForm) {
    return (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm((current) => ({ ...current, [field]: event.target.value }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const checked = validateOrderForm(form);
    if (!checked.ok) {
      setErrors(checked.errors);
      return;
    }
    setErrors({});
    setMessage(null);
    setPhase('submitting');
    const result = await placeOrder(lines, checked.form, keys.current.keyFor(lines, checked.form));
    if (!result.ok) {
      setPhase('idle');
      setMessage(
        result.reason === 'stock'
          ? STOCK_MESSAGE
          : result.reason === 'invalid'
            ? result.message
            : UNAVAILABLE_MESSAGE
      );
      return;
    }
    setPhase('redirecting');
    const url = await startPayment(
      items.map((item) => ({ productId: item.product.id, quantity: item.quantity }))
    );
    if (url === null) {
      setPhase('idle');
      setMessage(PAYMENT_MESSAGE);
      return;
    }
    window.location.href = url;
  }

  if (items.length === 0) {
    return (
      <section className="mx-auto max-w-3xl px-4 py-16 text-center">
        <h1 className="text-3xl font-bold text-granite">Votre panier</h1>
        <p className="mt-4 text-granite/70">Votre panier est vide pour l&apos;instant.</p>
        <Link
          href="/"
          className="mt-6 inline-flex rounded-full bg-forest px-6 py-3 text-sm font-semibold text-sand hover:bg-forest-light"
        >
          Retour à la boutique
        </Link>
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-6xl px-4 py-10">
      <h1 className="text-3xl font-bold text-granite">Votre panier</h1>
      <div className="mt-8 grid gap-10 lg:grid-cols-[1fr_24rem]">
        <ul className="divide-y divide-granite/10">
          {items.map(({ product, quantity }) => {
            const quoted = quoteByProduct.get(product.id);
            return (
              <li key={product.id} className="flex gap-4 py-5">
                <div className="relative h-24 w-24 flex-shrink-0 overflow-hidden rounded-lg bg-sand-dark">
                  {product.images[0] && (
                    <Image
                      src={product.images[0]}
                      alt={product.name}
                      fill
                      className="object-cover"
                      sizes="96px"
                    />
                  )}
                </div>
                <div className="flex flex-1 flex-col">
                  <Link
                    href={`/produits/${product.slug}`}
                    className="font-medium text-granite hover:text-forest"
                  >
                    {product.name}
                  </Link>
                  <span className="text-sm text-granite/60">
                    {quoted ? `${quoted.unitPriceEur.toFixed(2)} €` : '…'}
                  </span>
                  {quoted?.status === 'insufficient_stock' && (
                    <span role="alert" className="text-xs font-semibold text-red-700">
                      Stock insuffisant :{' '}
                      {quoted.availableQuantity === 0
                        ? 'produit épuisé'
                        : `${quoted.availableQuantity} disponible${quoted.availableQuantity > 1 ? 's' : ''}`}
                    </span>
                  )}
                  <div className="mt-auto flex items-center gap-2">
                    <button
                      type="button"
                      aria-label="Diminuer la quantité"
                      disabled={busy}
                      onClick={() => setQuantity(product.id, quantity - 1)}
                      className="flex h-8 w-8 items-center justify-center rounded-full border border-granite/20 hover:bg-granite/5"
                    >
                      <Minus size={14} />
                    </button>
                    <span className="w-6 text-center text-sm">{quantity}</span>
                    <button
                      type="button"
                      aria-label="Augmenter la quantité"
                      disabled={busy}
                      onClick={() => setQuantity(product.id, quantity + 1)}
                      className="flex h-8 w-8 items-center justify-center rounded-full border border-granite/20 hover:bg-granite/5"
                    >
                      <Plus size={14} />
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => removeItem(product.id)}
                      className="ml-auto text-xs text-granite/50 underline hover:text-bivouac"
                    >
                      Retirer
                    </button>
                  </div>
                </div>
                <span className="self-start text-sm font-semibold text-granite">
                  {quoted ? `${quoted.lineTotalEur.toFixed(2)} €` : '…'}
                </span>
              </li>
            );
          })}
        </ul>

        <form onSubmit={handleSubmit} noValidate className="space-y-4 rounded-2xl bg-sand p-5">
          <h2 className="text-lg font-semibold text-granite">Livraison</h2>
          <Field label="Email" error={errors.email}>
            <input
              type="email"
              autoComplete="email"
              value={form.email}
              onChange={update('email')}
              className={inputClass}
            />
          </Field>
          <Field label="Nom complet" error={errors.fullName}>
            <input
              autoComplete="name"
              value={form.fullName}
              onChange={update('fullName')}
              className={inputClass}
            />
          </Field>
          <Field label="Adresse" error={errors.line1}>
            <input
              autoComplete="address-line1"
              value={form.line1}
              onChange={update('line1')}
              className={inputClass}
            />
          </Field>
          <Field label="Complément d'adresse (facultatif)">
            <input
              autoComplete="address-line2"
              value={form.line2}
              onChange={update('line2')}
              className={inputClass}
            />
          </Field>
          <div className="grid grid-cols-[8rem_1fr] gap-3">
            <Field label="Code postal" error={errors.postalCode}>
              <input
                autoComplete="postal-code"
                value={form.postalCode}
                onChange={update('postalCode')}
                className={inputClass}
              />
            </Field>
            <Field label="Ville" error={errors.city}>
              <input
                autoComplete="address-level2"
                value={form.city}
                onChange={update('city')}
                className={inputClass}
              />
            </Field>
          </div>
          <Field label="Pays" error={errors.country}>
            <select
              autoComplete="country"
              value={form.country}
              onChange={update('country')}
              className={inputClass}
            >
              {SHIPPING_COUNTRIES.map((country) => (
                <option key={country.code} value={country.code}>
                  {country.label}
                </option>
              ))}
            </select>
          </Field>

          <div className="border-t border-granite/10 pt-4 text-sm text-granite/70">
            <div className="flex justify-between">
              <span>Sous-total</span>
              <span>{quote ? `${quote.subtotalEur.toFixed(2)} €` : '…'}</span>
            </div>
            <div className="flex justify-between">
              <span>Livraison</span>
              <span>
                {quote ? (quote.shippingEur === 0 ? 'Offerte' : `${quote.shippingEur.toFixed(2)} €`) : '…'}
              </span>
            </div>
            <div className="mt-2 flex justify-between text-base font-bold text-granite">
              <span>Total</span>
              <span>{quote ? `${quote.totalEur.toFixed(2)} €` : '…'}</span>
            </div>
          </div>

          {quoteStatus === 'error' && (
            <p role="alert" className="text-sm text-red-700">
              Impossible de vérifier votre panier pour le moment. Réessayez dans quelques instants.
            </p>
          )}
          {quote?.hasIssues && (
            <p role="alert" className="text-sm text-red-700">
              Ajustez les quantités signalées avant de commander.
            </p>
          )}
          {message && (
            <p role="alert" className="text-sm text-red-700">
              {message}
            </p>
          )}

          <button
            type="submit"
            disabled={!canOrder}
            className="flex w-full items-center justify-center rounded-full bg-bivouac py-3.5 text-base font-semibold text-white transition-transform duration-150 hover:bg-bivouac-dark active:scale-[0.98] disabled:opacity-60"
          >
            {phase === 'submitting'
              ? 'Enregistrement…'
              : phase === 'redirecting'
                ? 'Redirection vers le paiement…'
                : 'Commander et payer'}
          </button>
        </form>
      </div>
    </section>
  );
}

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm font-medium text-granite">
      {label}
      <span className="mt-1 block">{children}</span>
      {error && (
        <span role="alert" className="mt-1 block text-xs text-red-700">
          {error}
        </span>
      )}
    </label>
  );
}

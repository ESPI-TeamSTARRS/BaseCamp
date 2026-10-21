'use client';

import Image from 'next/image';
import Link from 'next/link';
import { AnimatePresence, motion } from 'framer-motion';
import { X, Minus, Plus, ShoppingBag } from 'lucide-react';
import { useCart } from '../context/CartContext';

export function CartDrawer() {
  const { isOpen, closeCart, items, quote, quoteStatus, setQuantity, removeItem } = useCart();

  // Tous les montants affichés viennent du devis du serveur, franco compris.
  const threshold = quote?.freeShippingThresholdEur ?? 0;
  const amountRemaining = quote?.amountRemainingForFreeShippingEur ?? 0;
  const progressPct = threshold > 0 ? Math.min(100, ((threshold - amountRemaining) / threshold) * 100) : 0;
  const quoteByProduct = new Map((quote?.lines ?? []).map((line) => [line.productId, line]));
  const canCheckout = quoteStatus === 'ready' && quote !== null && !quote.hasIssues;

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={closeCart}
            className="fixed inset-0 z-40 bg-granite/60"
            aria-hidden="true"
          />
          <motion.aside
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            role="dialog"
            aria-label="Panier"
            className="fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col bg-sand shadow-card-hover"
          >
            <div className="flex items-center justify-between border-b border-granite/10 px-5 py-4">
              <h2 className="flex items-center gap-2 text-lg font-semibold text-granite">
                <ShoppingBag size={20} className="text-forest" /> Votre panier
              </h2>
              <button
                type="button"
                onClick={closeCart}
                aria-label="Fermer le panier"
                className="flex h-10 w-10 items-center justify-center rounded-full hover:bg-granite/5"
              >
                <X size={20} />
              </button>
            </div>

            {quote && items.length > 0 && amountRemaining > 0 ? (
              <div className="px-5 py-3 text-sm">
                <p className="text-forest-deep">
                  Plus que <strong>{amountRemaining.toFixed(2)} €</strong> pour la livraison offerte (dès{' '}
                  {threshold.toFixed(2)} €) !
                </p>
                <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-granite/10">
                  <motion.div
                    className="h-full rounded-full bg-bivouac"
                    initial={{ width: 0 }}
                    animate={{ width: `${progressPct}%` }}
                    transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                  />
                </div>
              </div>
            ) : quote && items.length > 0 ? (
              <div className="px-5 py-3 text-sm font-medium text-forest-deep">
                🎉 Livraison offerte débloquée !
              </div>
            ) : null}

            <div className="flex-1 overflow-y-auto px-5 py-2">
              {items.length === 0 ? (
                <p className="py-12 text-center text-granite/60">
                  Votre panier est vide pour l&apos;instant.
                </p>
              ) : (
                <ul className="divide-y divide-granite/10">
                  {items.map(({ product, quantity }) => {
                    const quoted = quoteByProduct.get(product.id);
                    return (
                      <li key={product.id} className="flex gap-3 py-4">
                        <div className="relative h-20 w-20 flex-shrink-0 overflow-hidden rounded-lg bg-sand-dark">
                          {product.images[0] && (
                            <Image
                              src={product.images[0]}
                              alt={product.name}
                              fill
                              className="object-cover"
                              sizes="80px"
                            />
                          )}
                        </div>
                        <div className="flex flex-1 flex-col">
                          <span className="text-sm font-medium text-granite">{product.name}</span>
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
                              onClick={() => setQuantity(product.id, quantity - 1)}
                              className="flex h-7 w-7 items-center justify-center rounded-full border border-granite/20 hover:bg-granite/5"
                            >
                              <Minus size={13} />
                            </button>
                            <span className="w-6 text-center text-sm">{quantity}</span>
                            <button
                              type="button"
                              aria-label="Augmenter la quantité"
                              onClick={() => setQuantity(product.id, quantity + 1)}
                              className="flex h-7 w-7 items-center justify-center rounded-full border border-granite/20 hover:bg-granite/5"
                            >
                              <Plus size={13} />
                            </button>
                            <button
                              type="button"
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
              )}
            </div>

            {items.length > 0 && (
              <div className="border-t border-granite/10 px-5 py-4">
                {quoteStatus === 'error' && (
                  <p role="alert" className="mb-2 text-sm text-red-700">
                    Impossible de vérifier votre panier pour le moment. Réessayez dans quelques instants.
                  </p>
                )}
                {quote?.hasIssues && (
                  <p role="alert" className="mb-2 text-sm text-red-700">
                    Ajustez les quantités signalées avant de payer.
                  </p>
                )}
                <div className="flex justify-between text-sm text-granite/70">
                  <span>Sous-total</span>
                  <span>{quote ? `${quote.subtotalEur.toFixed(2)} €` : '…'}</span>
                </div>
                <div className="flex justify-between text-sm text-granite/70">
                  <span>Livraison</span>
                  <span>
                    {quote
                      ? quote.shippingEur === 0
                        ? 'Offerte'
                        : `${quote.shippingEur.toFixed(2)} €`
                      : '…'}
                  </span>
                </div>
                <div className="mt-2 flex justify-between text-base font-bold text-granite">
                  <span>Total</span>
                  <span>{quote ? `${quote.totalEur.toFixed(2)} €` : '…'}</span>
                </div>
                <Link
                  href="/panier"
                  onClick={closeCart}
                  aria-disabled={!canCheckout}
                  tabIndex={canCheckout ? undefined : -1}
                  className="mt-4 flex w-full items-center justify-center rounded-full bg-bivouac py-3.5 text-base font-semibold text-white transition-transform duration-150 hover:bg-bivouac-dark active:scale-[0.98] disabled:opacity-60 aria-disabled:pointer-events-none"
                >
                  Passer commande
                </Link>
              </div>
            )}
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

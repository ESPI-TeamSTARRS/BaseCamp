'use client';

import Image from 'next/image';
import { AnimatePresence, motion } from 'framer-motion';
import { X, Minus, Plus, ShoppingBag } from 'lucide-react';
import { useState } from 'react';
import { useCart, FREE_SHIPPING_THRESHOLD_EUR } from '@/context/CartContext';

export function CartDrawer() {
  const { isOpen, closeCart, items, subtotalEur, shippingEur, totalEur, amountRemainingForFreeShippingEur, setQuantity, removeItem } =
    useCart();
  const [isCheckingOut, setIsCheckingOut] = useState(false);

  const progressPct = Math.min(
    100,
    ((FREE_SHIPPING_THRESHOLD_EUR - amountRemainingForFreeShippingEur) / FREE_SHIPPING_THRESHOLD_EUR) * 100
  );

  async function handleCheckout() {
    setIsCheckingOut(true);
    try {
      const res = await fetch('/api/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lines: items.map((item) => ({ productId: item.product.id, quantity: item.quantity })),
        }),
      });
      const data = await res.json();
      if (data.url) {
        window.location.href = data.url;
      }
    } finally {
      setIsCheckingOut(false);
    }
  }

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

            {amountRemainingForFreeShippingEur > 0 ? (
              <div className="px-5 py-3 text-sm">
                <p className="text-forest-deep">
                  Plus que <strong>{amountRemainingForFreeShippingEur.toFixed(2)} €</strong> pour la livraison
                  offerte !
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
            ) : items.length > 0 ? (
              <div className="px-5 py-3 text-sm font-medium text-forest-deep">🎉 Livraison offerte débloquée !</div>
            ) : null}

            <div className="flex-1 overflow-y-auto px-5 py-2">
              {items.length === 0 ? (
                <p className="py-12 text-center text-granite/60">Votre panier est vide pour l&apos;instant.</p>
              ) : (
                <ul className="divide-y divide-granite/10">
                  {items.map(({ product, quantity, lineTotalEur }) => (
                    <li key={product.id} className="flex gap-3 py-4">
                      <div className="relative h-20 w-20 flex-shrink-0 overflow-hidden rounded-lg bg-sand-dark">
                        {product.images[0] && (
                          <Image src={product.images[0]} alt={product.name} fill className="object-cover" sizes="80px" />
                        )}
                      </div>
                      <div className="flex flex-1 flex-col">
                        <span className="text-sm font-medium text-granite">{product.name}</span>
                        <span className="text-sm text-granite/60">{product.priceEur.toFixed(2)} €</span>
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
                        {lineTotalEur.toFixed(2)} €
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {items.length > 0 && (
              <div className="border-t border-granite/10 px-5 py-4">
                <div className="flex justify-between text-sm text-granite/70">
                  <span>Sous-total</span>
                  <span>{subtotalEur.toFixed(2)} €</span>
                </div>
                <div className="flex justify-between text-sm text-granite/70">
                  <span>Livraison</span>
                  <span>{shippingEur === 0 ? 'Offerte' : `${shippingEur.toFixed(2)} €`}</span>
                </div>
                <div className="mt-2 flex justify-between text-base font-bold text-granite">
                  <span>Total</span>
                  <span>{totalEur.toFixed(2)} €</span>
                </div>
                <button
                  type="button"
                  onClick={handleCheckout}
                  disabled={isCheckingOut}
                  className="mt-4 flex w-full items-center justify-center rounded-full bg-bivouac py-3.5 text-base font-semibold text-white transition-transform duration-150 hover:bg-bivouac-dark active:scale-[0.98] disabled:opacity-60"
                >
                  {isCheckingOut ? 'Redirection…' : 'Passer au paiement sécurisé'}
                </button>
              </div>
            )}
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

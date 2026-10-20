'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  addLine,
  removeLine,
  sanitizeStoredLines,
  setLineQuantity,
  toCartProduct,
  type CartLine,
  type CartProduct,
} from '../lib/cart-lines';
import { fetchCartQuote, type CartQuote } from '../lib/cart-quote';
import type { Product } from '../types/product';

export type QuoteStatus = 'idle' | 'loading' | 'ready' | 'error';

interface CartContextValue {
  lines: CartLine[];
  isOpen: boolean;
  openCart: () => void;
  closeCart: () => void;
  /** Ajoute un produit ; sans effet si le produit est en rupture de stock. */
  addItem: (product: Product | CartProduct, quantity?: number) => void;
  removeItem: (productId: string) => void;
  setQuantity: (productId: string, quantity: number) => void;
  itemCount: number;
  items: Array<{ product: CartProduct; quantity: number }>;
  /** Devis du serveur (prix, livraison, franco, stock) : le panier local ne décide jamais d'un montant. */
  quote: CartQuote | null;
  quoteStatus: QuoteStatus;
}

const CartContext = createContext<CartContextValue | null>(null);
const STORAGE_KEY = 'basecamp-outdoor-cart-v2';

function isFullProduct(product: Product | CartProduct): product is Product {
  return 'description' in product;
}

export function CartProvider({ children }: { children: ReactNode }) {
  const [lines, setLines] = useState<CartLine[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [quote, setQuote] = useState<CartQuote | null>(null);
  const [quoteStatus, setQuoteStatus] = useState<QuoteStatus>('idle');

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored) setLines(sanitizeStoredLines(JSON.parse(stored)));
    } catch {
      // stockage indisponible ou corrompu : le panier reste simplement vide pour cette session
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(lines));
    } catch {
      // stockage indisponible : on ignore silencieusement, ce n'est pas bloquant
    }
  }, [lines]);

  // Chaque modification du panier redemande le devis au serveur (la dernière réponse l'emporte).
  useEffect(() => {
    let cancelled = false;
    if (lines.length === 0) {
      setQuote(null);
      setQuoteStatus('idle');
      return;
    }
    setQuoteStatus('loading');
    fetchCartQuote(lines).then((result) => {
      if (cancelled) return;
      if (result.ok) {
        setQuote(result.quote);
        setQuoteStatus('ready');
      } else {
        setQuoteStatus('error');
      }
    });
    return () => {
      cancelled = true;
    };
  }, [lines]);

  const addItem = useCallback((product: Product | CartProduct, quantity = 1) => {
    if (product.availability === 'out_of_stock') return;
    const cartProduct = isFullProduct(product) ? toCartProduct(product) : product;
    setLines((prev) => addLine(prev, cartProduct, quantity));
    setIsOpen(true);
  }, []);

  const removeItem = useCallback((productId: string) => {
    setLines((prev) => removeLine(prev, productId));
  }, []);

  const setQuantity = useCallback((productId: string, quantity: number) => {
    setLines((prev) => setLineQuantity(prev, productId, quantity));
  }, []);

  const itemCount = useMemo(() => lines.reduce((sum, l) => sum + l.quantity, 0), [lines]);

  const value: CartContextValue = {
    lines,
    isOpen,
    openCart: () => setIsOpen(true),
    closeCart: () => setIsOpen(false),
    addItem,
    removeItem,
    setQuantity,
    itemCount,
    items: lines,
    quote,
    quoteStatus,
  };

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart() {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart doit être utilisé à l'intérieur de <CartProvider>");
  return ctx;
}

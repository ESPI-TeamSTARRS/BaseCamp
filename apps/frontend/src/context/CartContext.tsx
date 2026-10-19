'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { products } from '../lib/products';
import type { Product } from '../types/product';

export const FREE_SHIPPING_THRESHOLD_EUR = 80;
export const STANDARD_SHIPPING_EUR = 5.9;

interface CartLine {
  productId: string;
  quantity: number;
}

interface CartContextValue {
  lines: CartLine[];
  isOpen: boolean;
  openCart: () => void;
  closeCart: () => void;
  addItem: (productId: string, quantity?: number) => void;
  removeItem: (productId: string) => void;
  setQuantity: (productId: string, quantity: number) => void;
  itemCount: number;
  items: Array<{ product: Product; quantity: number; lineTotalEur: number }>;
  subtotalEur: number;
  shippingEur: number;
  totalEur: number;
  amountRemainingForFreeShippingEur: number;
}

const CartContext = createContext<CartContextValue | null>(null);
const STORAGE_KEY = 'basecamp-outdoor-cart';

export function CartProvider({ children }: { children: ReactNode }) {
  const [lines, setLines] = useState<CartLine[]>([]);
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored) setLines(JSON.parse(stored));
    } catch {
      // stockage indisponible : le panier reste simplement vide pour cette session
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(lines));
    } catch {
      // stockage indisponible : on ignore silencieusement, ce n'est pas bloquant
    }
  }, [lines]);

  const addItem = useCallback((productId: string, quantity = 1) => {
    setLines((prev) => {
      const existing = prev.find((l) => l.productId === productId);
      if (existing) {
        return prev.map((l) =>
          l.productId === productId ? { ...l, quantity: Math.min(l.quantity + quantity, 10) } : l
        );
      }
      return [...prev, { productId, quantity }];
    });
    setIsOpen(true);
  }, []);

  const removeItem = useCallback((productId: string) => {
    setLines((prev) => prev.filter((l) => l.productId !== productId));
  }, []);

  const setQuantity = useCallback((productId: string, quantity: number) => {
    setLines((prev) =>
      prev
        .map((l) => (l.productId === productId ? { ...l, quantity: Math.max(1, Math.min(quantity, 10)) } : l))
        .filter((l) => l.quantity > 0)
    );
  }, []);

  const items = useMemo(
    () =>
      lines
        .map((line) => {
          const product = products.find((p) => p.id === line.productId);
          if (!product) return null;
          return { product, quantity: line.quantity, lineTotalEur: product.priceEur * line.quantity };
        })
        .filter((v): v is { product: Product; quantity: number; lineTotalEur: number } => v !== null),
    [lines]
  );

  const subtotalEur = useMemo(() => items.reduce((sum, item) => sum + item.lineTotalEur, 0), [items]);
  const shippingEur =
    subtotalEur >= FREE_SHIPPING_THRESHOLD_EUR || subtotalEur === 0 ? 0 : STANDARD_SHIPPING_EUR;
  const totalEur = subtotalEur + shippingEur;
  const amountRemainingForFreeShippingEur = Math.max(0, FREE_SHIPPING_THRESHOLD_EUR - subtotalEur);
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
    items,
    subtotalEur,
    shippingEur,
    totalEur,
    amountRemainingForFreeShippingEur,
  };

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart() {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart doit être utilisé à l'intérieur de <CartProvider>");
  return ctx;
}

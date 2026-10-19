'use client';

import { ShoppingBag } from 'lucide-react';
import { useCart } from '@/context/CartContext';

export function AddToCartButton({ productId, inStock }: { productId: string; inStock: boolean }) {
  const { addItem } = useCart();

  return (
    <button
      type="button"
      onClick={() => addItem(productId)}
      disabled={!inStock}
      className="flex w-full items-center justify-center gap-2 rounded-full bg-bivouac py-3.5 text-base font-semibold text-white transition-transform duration-150 hover:bg-bivouac-dark active:scale-[0.98] disabled:opacity-50"
    >
      <ShoppingBag size={18} />
      {inStock ? 'Ajouter au panier' : 'Rupture de stock'}
    </button>
  );
}

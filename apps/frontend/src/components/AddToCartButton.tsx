'use client';

import { ShoppingBag } from 'lucide-react';
import { useCart } from '../context/CartContext';
import type { Product } from '../types/product';

export function AddToCartButton({ product }: { product: Product }) {
  const { addItem } = useCart();
  const soldOut = product.availability === 'out_of_stock';

  return (
    <button
      type="button"
      onClick={() => addItem(product)}
      disabled={soldOut}
      className="flex w-full items-center justify-center gap-2 rounded-full bg-bivouac py-3.5 text-base font-semibold text-white transition-transform duration-150 hover:bg-bivouac-dark active:scale-[0.98] disabled:opacity-50"
    >
      <ShoppingBag size={18} />
      {soldOut ? 'Rupture de stock' : 'Ajouter au panier'}
    </button>
  );
}

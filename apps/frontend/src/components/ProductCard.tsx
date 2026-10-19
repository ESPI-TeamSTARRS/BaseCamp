'use client';

import Image from 'next/image';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { Star, ShoppingBag } from 'lucide-react';
import type { Product } from '../types/product';
import { TechBadgeList } from './TechBadge';
import { useCart } from '../context/CartContext';

export function ProductCard({ product }: { product: Product }) {
  const { addItem } = useCart();

  return (
    <motion.div
      whileHover={{ y: -4 }}
      transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
      className="group relative flex flex-col overflow-hidden rounded-card bg-white shadow-card transition-shadow duration-200 hover:shadow-card-hover"
    >
      <Link
        href={`/produits/${product.slug}`}
        className="relative block aspect-[4/3] bg-sand-dark overflow-hidden"
      >
        {product.images[0] ? (
          <Image
            src={product.images[0]}
            alt={product.name}
            fill
            sizes="(max-width: 768px) 100vw, 33vw"
            className="object-cover transition-transform duration-300 group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-granite/40">Visuel produit</div>
        )}
        {product.compareAtPriceEur && (
          <span className="absolute left-3 top-3 rounded-full bg-bivouac px-2.5 py-1 text-xs font-semibold text-white">
            Promo
          </span>
        )}
      </Link>

      <div className="flex flex-1 flex-col gap-2 p-4">
        <TechBadgeList specs={product.specs} size="sm" />

        <Link href={`/produits/${product.slug}`} className="mt-1">
          <h3 className="text-lg font-semibold text-granite leading-snug hover:text-forest transition-colors">
            {product.name}
          </h3>
        </Link>

        <p className="text-sm text-granite/70 line-clamp-2">{product.shortDescription}</p>

        <div className="flex items-center gap-1 text-xs text-granite/60">
          <Star size={13} className="fill-bivouac text-bivouac" />
          <span>
            {product.ratingValue.toFixed(1)} ({product.ratingCount} avis)
          </span>
        </div>

        <div className="mt-auto flex items-center justify-between pt-2">
          <div className="flex items-baseline gap-2">
            <span className="text-xl font-bold text-forest-deep">{product.priceEur.toFixed(2)} €</span>
            {product.compareAtPriceEur && (
              <span className="text-sm text-granite/40 line-through">
                {product.compareAtPriceEur.toFixed(2)} €
              </span>
            )}
          </div>

          <button
            type="button"
            onClick={() => addItem(product.id)}
            aria-label={`Ajouter ${product.name} au panier`}
            className="flex h-11 w-11 items-center justify-center rounded-full bg-forest text-sand transition-transform duration-150 hover:bg-forest-light active:scale-95"
          >
            <ShoppingBag size={18} />
          </button>
        </div>
      </div>
    </motion.div>
  );
}

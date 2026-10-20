'use client';

import Link from 'next/link';
import { ShoppingBag, Menu, Mountain } from 'lucide-react';
import { useState } from 'react';
import { useCart } from '../context/CartContext';
import { categoryLabels } from '../lib/categories';

export function Header() {
  const { itemCount, openCart } = useCart();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <header className="sticky top-0 z-30 border-b border-granite/10 bg-sand/95 backdrop-blur-sm">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
        <Link href="/" className="flex items-center gap-2 text-lg font-bold text-forest-deep">
          <Mountain size={22} className="text-bivouac" />
          Basecamp Outdoor
        </Link>

        <nav className="hidden items-center gap-6 text-sm font-medium text-granite md:flex">
          {Object.entries(categoryLabels).map(([slug, label]) => (
            <Link key={slug} href={`/categories/${slug}`} className="hover:text-forest transition-colors">
              {label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={openCart}
            aria-label={`Panier, ${itemCount} article${itemCount > 1 ? 's' : ''}`}
            className="relative flex h-11 w-11 items-center justify-center rounded-full text-granite transition-colors hover:bg-granite/5"
          >
            <ShoppingBag size={20} />
            {itemCount > 0 && (
              <span className="absolute -right-0.5 -top-0.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-bivouac px-1 text-[11px] font-bold text-white">
                {itemCount}
              </span>
            )}
          </button>
          <button
            type="button"
            onClick={() => setMobileMenuOpen((v) => !v)}
            aria-label="Menu de navigation"
            className="flex h-11 w-11 items-center justify-center rounded-full text-granite hover:bg-granite/5 md:hidden"
          >
            <Menu size={20} />
          </button>
        </div>
      </div>

      {mobileMenuOpen && (
        <nav className="flex flex-col border-t border-granite/10 bg-sand px-4 py-2 md:hidden">
          {Object.entries(categoryLabels).map(([slug, label]) => (
            <Link
              key={slug}
              href={`/categories/${slug}`}
              onClick={() => setMobileMenuOpen(false)}
              className="py-3 text-sm font-medium text-granite border-b border-granite/5 last:border-0"
            >
              {label}
            </Link>
          ))}
        </nav>
      )}
    </header>
  );
}

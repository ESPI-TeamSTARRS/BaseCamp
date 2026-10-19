import Link from 'next/link';
import { Mountain } from 'lucide-react';
import { categoryLabels } from '@/lib/products';

export function Footer() {
  return (
    <footer className="bg-granite text-sand/80">
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-12 sm:grid-cols-2 md:grid-cols-4">
        <div>
          <div className="flex items-center gap-2 text-lg font-bold text-sand">
            <Mountain size={20} className="text-bivouac" />
            Basecamp Outdoor
          </div>
          <p className="mt-3 text-sm text-sand/60">
            Équipement outdoor haut de gamme pour le bivouac et la grande randonnée en autonomie.
          </p>
        </div>

        <div>
          <h2 className="text-sm font-semibold text-sand">Catégories</h2>
          <ul className="mt-3 space-y-2 text-sm">
            {Object.entries(categoryLabels).map(([slug, label]) => (
              <li key={slug}>
                <Link href={`/categories/${slug}`} className="hover:text-bivouac transition-colors">
                  {label}
                </Link>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h2 className="text-sm font-semibold text-sand">Service client</h2>
          <ul className="mt-3 space-y-2 text-sm">
            <li><Link href="/suivi" className="hover:text-bivouac transition-colors">Suivre ma commande</Link></li>
            <li><Link href="/contact" className="hover:text-bivouac transition-colors">Contact</Link></li>
            <li><Link href="/cgv" className="hover:text-bivouac transition-colors">CGV</Link></li>
          </ul>
        </div>

        <div>
          <h2 className="text-sm font-semibold text-sand">Légal</h2>
          <ul className="mt-3 space-y-2 text-sm">
            <li><Link href="/confidentialite" className="hover:text-bivouac transition-colors">Confidentialité</Link></li>
            <li><Link href="/mentions-legales" className="hover:text-bivouac transition-colors">Mentions légales</Link></li>
          </ul>
        </div>
      </div>
      <div className="border-t border-sand/10 py-4 text-center text-xs text-sand/50">
        © {new Date().getFullYear()} Basecamp Outdoor. Tous droits réservés.
      </div>
    </footer>
  );
}

import { notFound } from 'next/navigation';
import type { Metadata } from 'next';
import { ProductCard } from '../../../components/ProductCard';
import { categoryLabels, getProductsByCategory } from '../../../lib/products';
import { truncateDescription } from '../../../lib/seo';
import type { ProductCategory } from '../../../types/product';

interface Props {
  params: { slug: string };
}

function isValidCategory(slug: string): slug is ProductCategory {
  return slug in categoryLabels;
}

export function generateStaticParams() {
  return Object.keys(categoryLabels).map((slug) => ({ slug }));
}

export function generateMetadata({ params }: Props): Metadata {
  if (!isValidCategory(params.slug)) return {};
  const label = categoryLabels[params.slug];
  const productCount = getProductsByCategory(params.slug).length;
  const description = truncateDescription(
    `Découvrez notre sélection ${label.toLowerCase()} (${productCount} produits) pour le bivouac et la grande randonnée en autonomie. Expédition 24/48h, retours gratuits sous 30 jours, garantie aventure et déchirure incluse.`
  );
  return {
    title: label,
    description,
    alternates: { canonical: `/categories/${params.slug}` },
  };
}

export default function CategoryPage({ params }: Props) {
  if (!isValidCategory(params.slug)) notFound();

  const label = categoryLabels[params.slug];
  const categoryProducts = getProductsByCategory(params.slug);

  return (
    <section className="mx-auto max-w-6xl px-4 py-12">
      <nav aria-label="Fil d'Ariane" className="mb-4 text-sm text-granite/60">
        <a href="/" className="hover:text-forest">
          Accueil
        </a>{' '}
        <span className="mx-1">/</span> {label}
      </nav>
      <h1 className="mb-6 text-3xl font-bold text-granite">{label}</h1>
      <h2 className="mb-6 text-sm font-medium uppercase tracking-wide text-granite/50">
        {categoryProducts.length} produit{categoryProducts.length > 1 ? 's' : ''} disponible
        {categoryProducts.length > 1 ? 's' : ''}
      </h2>

      {categoryProducts.length === 0 ? (
        <p className="text-granite/60">Aucun produit disponible dans cette catégorie pour le moment.</p>
      ) : (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {categoryProducts.map((product) => (
            <ProductCard key={product.id} product={product} />
          ))}
        </div>
      )}
    </section>
  );
}

import { notFound } from 'next/navigation';
import type { Metadata } from 'next';
import { CatalogUnavailable } from '../../../components/CatalogUnavailable';
import { ProductCard } from '../../../components/ProductCard';
import { categoryLabels, isProductCategory } from '../../../lib/categories';
import { truncateDescription } from '../../../lib/seo';
import { fetchAllProducts } from '../../../lib/shop-api';

interface Props {
  params: { slug: string };
}

// Le catalogue vient de l'API à chaque requête : rien n'est figé au build.
export const dynamic = 'force-dynamic';

export function generateMetadata({ params }: Props): Metadata {
  if (!isProductCategory(params.slug)) return {};
  const label = categoryLabels[params.slug];
  const description = truncateDescription(
    `Découvrez notre sélection ${label.toLowerCase()} pour le bivouac et la grande randonnée en autonomie. Expédition 24/48h, retours gratuits sous 30 jours, garantie aventure et déchirure incluse.`
  );
  return {
    title: label,
    description,
    alternates: { canonical: `/categories/${params.slug}` },
  };
}

export default async function CategoryPage({ params }: Props) {
  if (!isProductCategory(params.slug)) notFound();

  const label = categoryLabels[params.slug];
  const catalog = await fetchAllProducts(params.slug);
  const categoryProducts = catalog.ok ? catalog.products : [];

  return (
    <section className="mx-auto max-w-6xl px-4 py-12">
      <nav aria-label="Fil d'Ariane" className="mb-4 text-sm text-granite/60">
        <a href="/" className="hover:text-forest">
          Accueil
        </a>{' '}
        <span className="mx-1">/</span> {label}
      </nav>
      <h1 className="mb-6 text-3xl font-bold text-granite">{label}</h1>

      {!catalog.ok ? (
        <CatalogUnavailable />
      ) : categoryProducts.length === 0 ? (
        <p className="text-granite/60">Aucun produit disponible dans cette catégorie pour le moment.</p>
      ) : (
        <>
          <h2 className="mb-6 text-sm font-medium uppercase tracking-wide text-granite/50">
            {categoryProducts.length} produit{categoryProducts.length > 1 ? 's' : ''}
          </h2>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {categoryProducts.map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
          </div>
        </>
      )}
    </section>
  );
}

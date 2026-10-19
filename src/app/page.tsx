import { Hero } from '@/components/Hero';
import { ReassuranceBar } from '@/components/ReassuranceBar';
import { ProductCard } from '@/components/ProductCard';
import { JsonLd } from '@/components/JsonLd';
import { products, categoryLabels } from '@/lib/products';

export default function HomePage() {
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || 'https://basecamp-outdoor.fr';

  return (
    <>
      <JsonLd
        data={{
          '@context': 'https://schema.org',
          '@type': 'OnlineStore',
          name: 'Basecamp Outdoor',
          url: siteUrl,
          description: "Équipement outdoor haut de gamme pour le bivouac et la grande randonnée en autonomie.",
        }}
      />

      <Hero />
      <ReassuranceBar />

      <section className="mx-auto max-w-6xl px-4 py-16">
        <div className="mb-8 flex items-baseline justify-between">
          <h2 className="text-2xl font-bold text-granite">Les essentiels du bivouac</h2>
        </div>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {products.slice(0, 8).map((product) => (
            <ProductCard key={product.id} product={product} />
          ))}
        </div>
      </section>

      <section className="bg-forest-deep/5 py-16">
        <div className="mx-auto max-w-6xl px-4">
          <h2 className="mb-8 text-2xl font-bold text-granite">Explorer par catégorie</h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-5">
            {Object.entries(categoryLabels).map(([slug, label]) => (
              <a
                key={slug}
                href={`/categories/${slug}`}
                className="flex items-center justify-center rounded-card bg-forest px-4 py-8 text-center text-sm font-semibold text-sand shadow-card transition-transform duration-150 hover:-translate-y-1 hover:bg-forest-light"
              >
                {label}
              </a>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}

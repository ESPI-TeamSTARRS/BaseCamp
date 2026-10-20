import Link from 'next/link';
import { notFound } from 'next/navigation';
import type { Metadata } from 'next';
import Image from 'next/image';
import { Star, Truck, ShieldCheck, RotateCcw } from 'lucide-react';
import { TechBadgeList } from '../../../components/TechBadge';
import { JsonLd } from '../../../components/JsonLd';
import { AddToCartButton } from '../../../components/AddToCartButton';
import { CatalogUnavailable } from '../../../components/CatalogUnavailable';
import { categoryLabels } from '../../../lib/categories';
import { fetchProductBySlug } from '../../../lib/shop-api';
import { buildProductMetaDescription } from '../../../lib/seo';

interface Props {
  params: Promise<{ slug: string }>;
}

// Le catalogue vient de l'API à chaque requête : rien n'est figé au build.
export const dynamic = 'force-dynamic';

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const result = await fetchProductBySlug(slug);
  const product = result.ok ? result.product : null;
  if (!product) return {};
  const description = buildProductMetaDescription(product);
  return {
    title: product.name,
    description,
    alternates: { canonical: `/produits/${product.slug}` },
    openGraph: {
      title: product.name,
      description,
      images: product.images.length ? [{ url: product.images[0] }] : undefined,
    },
  };
}

export default async function ProductPage({ params }: Props) {
  const { slug } = await params;
  const result = await fetchProductBySlug(slug);
  if (!result.ok) {
    return (
      <section className="mx-auto max-w-6xl px-4 py-12">
        <CatalogUnavailable />
      </section>
    );
  }
  const product = result.product;
  if (!product) notFound();

  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || 'https://basecamp-outdoor.fr';
  const categoryLabel = categoryLabels[product.category];

  return (
    <>
      <JsonLd
        data={{
          '@context': 'https://schema.org',
          '@type': 'BreadcrumbList',
          itemListElement: [
            { '@type': 'ListItem', position: 1, name: 'Accueil', item: siteUrl },
            {
              '@type': 'ListItem',
              position: 2,
              name: categoryLabel,
              item: `${siteUrl}/categories/${product.category}`,
            },
            {
              '@type': 'ListItem',
              position: 3,
              name: product.name,
              item: `${siteUrl}/produits/${product.slug}`,
            },
          ],
        }}
      />
      <JsonLd
        data={{
          '@context': 'https://schema.org',
          '@type': 'Product',
          name: product.name,
          sku: product.id,
          image: product.images.map((img) => `${siteUrl}${img}`),
          description: product.description,
          brand: { '@type': 'Brand', name: 'Basecamp Outdoor' },
          aggregateRating: {
            '@type': 'AggregateRating',
            ratingValue: product.ratingValue,
            reviewCount: product.ratingCount,
          },
          offers: {
            '@type': 'Offer',
            url: `${siteUrl}/produits/${product.slug}`,
            priceCurrency: 'EUR',
            price: product.priceEur.toFixed(2),
            availability:
              product.availability !== 'out_of_stock'
                ? 'https://schema.org/InStock'
                : 'https://schema.org/OutOfStock',
            shippingDetails: {
              '@type': 'OfferShippingDetails',
              shippingRate: { '@type': 'MonetaryAmount', value: '0.00', currency: 'EUR' },
              deliveryTime: {
                '@type': 'ShippingDeliveryTime',
                handlingTime: { '@type': 'QuantitativeValue', minValue: 0, maxValue: 1, unitCode: 'DAY' },
                transitTime: { '@type': 'QuantitativeValue', minValue: 1, maxValue: 2, unitCode: 'DAY' },
              },
            },
            hasMerchantReturnPolicy: {
              '@type': 'MerchantReturnPolicy',
              applicableCountry: 'FR',
              returnPolicyCategory: 'https://schema.org/MerchantReturnFiniteReturnWindow',
              merchantReturnDays: 30,
              returnMethod: 'https://schema.org/ReturnByMail',
              returnFees: 'https://schema.org/FreeReturn',
            },
          },
        }}
      />

      <section className="mx-auto max-w-6xl px-4 py-8 pb-28 sm:pb-12">
        <nav aria-label="Fil d'Ariane" className="mb-4 text-sm text-granite/60">
          <Link href="/" className="hover:text-forest">
            Accueil
          </Link>{' '}
          <span className="mx-1">/</span>
          <a href={`/categories/${product.category}`} className="hover:text-forest">
            {categoryLabel}
          </a>{' '}
          <span className="mx-1">/</span> {product.name}
        </nav>

        <div className="grid grid-cols-1 gap-10 lg:grid-cols-2">
          <div className="relative aspect-square overflow-hidden rounded-card bg-sand-dark">
            {product.images[0] ? (
              <Image
                src={product.images[0]}
                alt={product.name}
                fill
                className="object-cover"
                sizes="(max-width: 1024px) 100vw, 50vw"
                priority
              />
            ) : (
              <div className="flex h-full items-center justify-center text-granite/40">Visuel produit</div>
            )}
          </div>

          {/* Informations clés au-dessus de la ligne de flottaison : titre, prix, badges, CTA */}
          <div className="flex flex-col gap-4">
            <h1 className="text-3xl font-bold text-granite">{product.name}</h1>

            <div className="flex items-center gap-2 text-sm text-granite/60">
              <div className="flex items-center gap-1">
                <Star size={15} className="fill-bivouac text-bivouac" />
                <span>{product.ratingValue.toFixed(1)}</span>
              </div>
              <span>·</span>
              <span>{product.ratingCount} avis</span>
            </div>

            <TechBadgeList specs={product.specs} size="md" />

            <div className="flex items-baseline gap-3">
              <span className="text-3xl font-bold text-forest-deep">{product.priceEur.toFixed(2)} €</span>
              {product.compareAtPriceEur && (
                <span className="text-lg text-granite/40 line-through">
                  {product.compareAtPriceEur.toFixed(2)} €
                </span>
              )}
            </div>

            <p className="text-granite/70">{product.shortDescription}</p>

            <div className="hidden sm:block">
              <AddToCartButton product={product} />
            </div>

            <ul className="mt-2 space-y-2 text-sm text-granite/70">
              <li className="flex items-center gap-2">
                <Truck size={16} className="text-bivouac" /> Expédition en 24/48h
              </li>
              <li className="flex items-center gap-2">
                <ShieldCheck size={16} className="text-bivouac" /> Garantie aventure & déchirure
              </li>
              <li className="flex items-center gap-2">
                <RotateCcw size={16} className="text-bivouac" /> Retours gratuits sous 30 jours
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-12 max-w-3xl">
          <h2 className="mb-3 text-xl font-semibold text-granite">Description détaillée</h2>
          <p className="text-granite/80 leading-relaxed">{product.description}</p>

          {product.specs.material && (
            <p className="mt-4 text-sm text-granite/60">
              <strong className="text-granite">Matériau :</strong> {product.specs.material}
            </p>
          )}
        </div>
      </section>

      {/* Add to Cart sticky mobile pour conversion sans scroll */}
      <div className="fixed inset-x-0 bottom-0 z-20 flex items-center gap-3 border-t border-granite/10 bg-sand/95 p-4 backdrop-blur-sm sm:hidden">
        <div className="flex-1">
          <span className="block text-lg font-bold text-forest-deep">{product.priceEur.toFixed(2)} €</span>
        </div>
        <div className="flex-1">
          <AddToCartButton product={product} />
        </div>
      </div>
    </>
  );
}

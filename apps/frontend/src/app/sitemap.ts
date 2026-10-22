import type { MetadataRoute } from 'next';
import { categorySlugs } from '../lib/categories';
import { indexablePages } from '../lib/footer-links';
import { fetchAllProducts } from '../lib/shop-api';

// Généré à la demande : le catalogue vient de l'API et n'existe pas au moment du build.
export const dynamic = 'force-dynamic';

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || 'https://basecamp-outdoor.fr';

  const staticRoutes: MetadataRoute.Sitemap = [
    { url: siteUrl, lastModified: new Date(), changeFrequency: 'daily', priority: 1 },
  ];

  const pageRoutes: MetadataRoute.Sitemap = indexablePages.map((path) => ({
    url: `${siteUrl}${path}`,
    lastModified: new Date(),
    changeFrequency: 'yearly',
    priority: 0.3,
  }));

  const categoryRoutes: MetadataRoute.Sitemap = categorySlugs.map((slug) => ({
    url: `${siteUrl}/categories/${slug}`,
    lastModified: new Date(),
    changeFrequency: 'weekly',
    priority: 0.8,
  }));

  // Si l'API est arrêtée, le sitemap reste valide sans les fiches produit.
  const catalog = await fetchAllProducts();
  const productRoutes: MetadataRoute.Sitemap = catalog.ok
    ? catalog.products.map((product) => ({
        url: `${siteUrl}/produits/${product.slug}`,
        lastModified: new Date(),
        changeFrequency: 'weekly',
        priority: 0.7,
      }))
    : [];

  return [...staticRoutes, ...categoryRoutes, ...pageRoutes, ...productRoutes];
}

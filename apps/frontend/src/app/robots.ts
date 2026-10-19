import type { MetadataRoute } from 'next';

export default function robots(): MetadataRoute.Robots {
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || 'https://basecamp-outdoor.fr';
  return {
    rules: { userAgent: '*', allow: '/', disallow: ['/api/', '/success'] },
    sitemap: `${siteUrl}/sitemap.xml`,
  };
}

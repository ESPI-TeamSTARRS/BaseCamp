/** @type {import('next').NextConfig} */

// Origine admin : jamais indexee, jamais encadree, aucun script ni cadre tiers.
// La camera (lecture de QR code, ecrans a venir) n'est autorisee que pour cette origine.
const contentSecurityPolicy = `
  default-src 'self';
  script-src 'self' 'unsafe-inline';
  frame-src 'none';
  connect-src 'self';
  img-src 'self' data: blob:;
  style-src 'self' 'unsafe-inline';
  font-src 'self' data:;
  object-src 'none';
  base-uri 'self';
  form-action 'self';
  frame-ancestors 'none';
  block-all-mixed-content;
  upgrade-insecure-requests;
`.replace(/\s{2,}/g, ' ').trim();

const securityHeaders = [
  { key: 'X-Robots-Tag', value: 'noindex, nofollow, noarchive' },
  { key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains' },
  { key: 'X-Frame-Options', value: 'DENY' },
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'Referrer-Policy', value: 'no-referrer' },
  { key: 'Permissions-Policy', value: 'camera=(self), microphone=(), geolocation=(), payment=()' },
  { key: 'Content-Security-Policy', value: contentSecurityPolicy },
];

const nextConfig = {
  reactStrictMode: true,
  output: 'standalone', // requis par le conteneur non-root multi-stage (voir Dockerfile)
  poweredByHeader: false,
  async headers() {
    return [{ source: '/:path*', headers: securityHeaders }];
  },
};

export default nextConfig;

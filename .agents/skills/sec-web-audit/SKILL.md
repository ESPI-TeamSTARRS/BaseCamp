---
name: sec-web-audit
description: Web application defensive security auditor & attack surface scanner: audits HTTP security headers (CSP, HSTS, X-Frame-Options), rate-limiting mechanisms, sensitive endpoints exposure, and API abuse prevention.
category: security
---

# Web Security & Attack Surface Auditor (sec-web-audit)

Framework d'audit de sécurité défensif et de réduction de surface d'attaque pour applications web modernes (Next.js, Node.js, SPA, APIs).

## 1. Audit des En-têtes HTTP de Sécurité (Target Grade A+ SecurityHeaders)

Tout déploiement web de production doit comporter ces en-têtes configurés dans le framework (`next.config.mjs`) ou le reverse-proxy :

```javascript
// Configuration recommandée pour Next.js (next.config.mjs)
const securityHeaders = [
  {
    key: 'X-DNS-Prefetch-Control',
    value: 'on'
  },
  {
    key: 'Strict-Transport-Security',
    value: 'max-age=63072000; includeSubDomains; preload'
  },
  {
    key: 'X-Frame-Options',
    value: 'DENY'
  },
  {
    key: 'X-Content-Type-Options',
    value: 'nosniff'
  },
  {
    key: 'Referrer-Policy',
    value: 'strict-origin-when-cross-origin'
  },
  {
    key: 'Permissions-Policy',
    value: 'camera=(), microphone=(), geolocation=(), payment=(self "https://js.stripe.com")'
  },
  {
    key: 'Content-Security-Policy',
    value: `
      default-src 'self';
      script-src 'self' 'unsafe-eval' 'unsafe-inline' https://js.stripe.com;
      frame-src 'self' https://js.stripe.com https://hooks.stripe.com;
      connect-src 'self' https://api.stripe.com https://checkout.stripe.com;
      img-src 'self' data: https: blob:;
      style-src 'self' 'unsafe-inline';
      font-src 'self' data:;
      object-src 'none';
      base-uri 'self';
      form-action 'self' https://checkout.stripe.com;
      frame-ancestors 'none';
      block-all-mixed-content;
      upgrade-insecure-requests;
    `.replace(/\s{2,}/g, ' ').trim()
  }
];
```

## 2. Détection des Fichiers et Dossiers Exposés

Vérifier qu'aucune requête HTTP ne peut exfiltrer :
- Fichiers `.env`, `.env.local`, `.env.production`
- Dossiers de versioning `.git/`, `.gitignore`
- Fichiers de configuration de conteneur `docker-compose.yml`, `Dockerfile`
- Fichiers de cartographie du code `.map` (Source maps de production)

## 3. Mécanisme Anti-Abus & Rate-Limiting sur les Routes Publiques

Sur toute route créant des sessions externes ou consommant des ressources (`/api/checkout`, `/api/contact`, `/api/login`) :
- **Principe du Token Bucket ou Sliding Window** : Limiter les requêtes par IP (ex: maximum 10 requêtes de checkout par minute par IP).
- Réponse en cas de dépassement : `HTTP 429 Too Many Requests` avec en-tête `Retry-After`.

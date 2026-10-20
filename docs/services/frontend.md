# Front `apps/frontend`

## Rôle
Vitrine Next.js (App Router) : catalogue, fiches produit, panier, pages légales, SEO.

## Stack
Next.js 16 (App Router, React 19, Turbopack), TypeScript strict, Tailwind CSS, Framer Motion, Zod. ESLint 9 en configuration plate (`eslint.config.mjs`, `eslint .`), Node 20.9 ou plus.

Les paramètres de route (`params`) sont asynchrones (`await params`). Les visuels du catalogue sont servis par la passerelle sous `/media` (même origine) : `images.remotePatterns` reste vide, sans domaine générique, et l'optimiseur d'images est désactivé. L'audit `npm audit --omit=dev --audit-level=high` est bloquant en CI (job `frontend`).

## Organisation
`src/app` (routes), `src/components`, `src/context` (panier), `src/lib` (utilitaires métier), `src/types`.

## Qualité
`npm run quality` (ESLint sans warning, Prettier, `tsc`), `npm run test:coverage` (Vitest, seuil 80 %). Tests colocalisés dans `__tests__/`.

## Configuration
Variables d'environnement décrites dans `apps/frontend/.env.example`; aucune clé privée n'est exposée au navigateur.

## Design
Palette : vert forêt `#1E3A2F`, orange bivouac `#E05638`, neutres pierre et sable. Badges techniques sur les produits (poids, imperméabilité, température de confort, matériau). Conception mobile first.

# Front `apps/frontend`

## Rôle
Vitrine Next.js (App Router) : catalogue, fiches produit, panier, pages légales, SEO.

## Stack
Next.js 14, TypeScript strict, Tailwind CSS, Framer Motion, Zod.

## Organisation
`src/app` (routes), `src/components`, `src/context` (panier), `src/lib` (utilitaires métier), `src/types`.

## Qualité
`npm run quality` (ESLint sans warning, Prettier, `tsc`), `npm run test:coverage` (Vitest, seuil 80 %). Tests colocalisés dans `__tests__/`.

## Configuration
Variables d'environnement décrites dans `apps/frontend/.env.example`; aucune clé privée n'est exposée au navigateur.

## Design
Palette : vert forêt `#1E3A2F`, orange bivouac `#E05638`, neutres pierre et sable. Badges techniques sur les produits (poids, imperméabilité, température de confort, matériau). Conception mobile first.

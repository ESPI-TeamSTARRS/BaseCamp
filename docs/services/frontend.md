# Front `apps/frontend`

## Rôle
Vitrine Next.js (App Router) : catalogue, fiches produit, panier, pages légales, SEO.

## Stack
Next.js 16 (App Router, React 19, Turbopack), TypeScript strict, Tailwind CSS, Framer Motion, Zod. ESLint 9 en configuration plate (`eslint.config.mjs`, `eslint .`), Node 20.9 ou plus.

Les paramètres de route (`params`) sont asynchrones (`await params`). Les visuels du catalogue sont servis par la passerelle sous `/media` (même origine) : `images.remotePatterns` reste vide, sans domaine générique, et l'optimiseur d'images est désactivé. L'audit `npm audit --omit=dev --audit-level=high` est bloquant en CI (job `frontend`).

## Comptes
Pages `/compte/inscription` (formulaire, états d'erreur sans détail technique) et `/compte/verification` (jeton lu dans le fragment d'URL `#token=`, retiré de la barre d'adresse avant l'appel). Les appels vont à `/api/auth/register` et `/api/auth/verify-email` par la passerelle (même origine). La logique testée est dans `src/lib/account-api.ts` et `src/lib/registration-flow.ts`; les composants `RegistrationForm` et `EmailVerification` ne font que l'affichage.

Réinitialisation du mot de passe : pages `/compte/mot-de-passe-oublie` (saisie de l'adresse; le message de succès est le même que le compte existe ou non) et `/compte/reinitialiser` (jeton dans le fragment `#token=`, retiré de la barre d'adresse avant tout appel; mot de passe et confirmation, mêmes règles que l'inscription, refus serveur affiché sur le champ; lien invalide, expiré ou déjà utilisé : un seul message). Appels à `/api/auth/password/forgot` et `/api/auth/password/reset`; logique testée dans `src/lib/account-api.ts` et `src/lib/password-reset-flow.ts`, composants `ForgotPasswordForm` et `ResetPasswordForm`.

Page `/compte/connexion` : `POST /api/auth/login` par la passerelle (`src/lib/login-api.ts`, `src/lib/login-flow.ts`, composant `LoginForm`). Un refus affiche toujours « Email ou mot de passe incorrect. », sans distinguer la cause. Le jeton d'accès est gardé **uniquement en mémoire** du module `src/lib/session-store.ts` (jamais `localStorage`, `sessionStorage` ni un cookie lisible par le script; un rechargement complet de la page l'efface); le jeton de rafraîchissement est un cookie `HttpOnly` que le script ne voit pas.

## Organisation
`src/app` (routes), `src/components`, `src/context` (panier), `src/lib` (utilitaires métier), `src/types`.

## Qualité
`npm run quality` (ESLint sans warning, Prettier, `tsc`), `npm run test:coverage` (Vitest, seuil 80 %). Tests colocalisés dans `__tests__/`.

## Configuration
Variables d'environnement décrites dans `apps/frontend/.env.example`; aucune clé privée n'est exposée au navigateur.

## Design
Palette : vert forêt `#1E3A2F`, orange bivouac `#E05638`, neutres pierre et sable. Badges techniques sur les produits (poids, imperméabilité, température de confort, matériau). Conception mobile first.

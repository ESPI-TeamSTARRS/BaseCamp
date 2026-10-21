# Front `apps/frontend`

## Rôle
Vitrine Next.js (App Router) : catalogue, fiches produit, panier et commande, paiement simulé, pages légales, SEO.

## Stack
Next.js 16 (App Router, React 19, Turbopack), TypeScript strict, Tailwind CSS, Framer Motion, Zod. ESLint 9 en configuration plate (`eslint.config.mjs`, `eslint .`), Node 20.9 ou plus.

Les paramètres de route (`params`) sont asynchrones (`await params`). Les visuels du catalogue sont servis par la passerelle sous `/media` (même origine) : `images.remotePatterns` reste vide, sans domaine générique, et l'optimiseur d'images est désactivé. L'audit `npm audit --omit=dev --audit-level=high` est bloquant en CI (job `frontend`).

## Comptes
Pages `/compte/inscription` (formulaire, états d'erreur sans détail technique) et `/compte/verification` (jeton lu dans le fragment d'URL `#token=`, retiré de la barre d'adresse avant l'appel). Les appels vont à `/api/auth/register` et `/api/auth/verify-email` par la passerelle (même origine). La logique testée est dans `src/lib/account-api.ts` et `src/lib/registration-flow.ts`; les composants `RegistrationForm` et `EmailVerification` ne font que l'affichage.

Réinitialisation du mot de passe : pages `/compte/mot-de-passe-oublie` (saisie de l'adresse; le message de succès est le même que le compte existe ou non) et `/compte/reinitialiser` (jeton dans le fragment `#token=`, retiré de la barre d'adresse avant tout appel; mot de passe et confirmation, mêmes règles que l'inscription, refus serveur affiché sur le champ; lien invalide, expiré ou déjà utilisé : un seul message). Appels à `/api/auth/password/forgot` et `/api/auth/password/reset`; logique testée dans `src/lib/account-api.ts` et `src/lib/password-reset-flow.ts`, composants `ForgotPasswordForm` et `ResetPasswordForm`.

Page `/compte/connexion` : `POST /api/auth/login` par la passerelle (`src/lib/login-api.ts`, `src/lib/login-flow.ts`, composant `LoginForm`). Un refus affiche toujours « Email ou mot de passe incorrect. », sans distinguer la cause. Le jeton d'accès est gardé **uniquement en mémoire** du module `src/lib/session-store.ts` (jamais `localStorage`, `sessionStorage` ni un cookie lisible par le script; un rechargement complet de la page l'efface); le jeton de rafraîchissement est un cookie `HttpOnly` que le script ne voit pas.

Session persistante : le composant `SessionKeeper` (monté dans le layout) retrouve la session au chargement de la page par `POST /api/auth/refresh` (`src/lib/session-api.ts`, avec l'en-tête `X-Requested-With`) et la rafraîchit en silence une minute avant l'expiration du jeton d'accès (`src/lib/session-keeper.ts`). Un seul rafraîchissement est en vol à la fois par onglet (sinon le serveur verrait un rejeu). Un 401 sur une session ouverte renvoie une seule fois vers `/compte/connexion`, sans nouvelle tentative (pas de boucle); un visiteur sans cookie reste anonyme sans redirection; une panne du service est retentée trois fois au plus. Le bouton de l'en-tête devient « Me déconnecter » quand une session est ouverte : il appelle `POST /api/auth/logout` (idempotent) puis efface le jeton en mémoire.

## Suivi de commande
`/suivi` remplace l'ancien texte statique par un formulaire (numéro `BC-…` et email) qui appelle `POST /api/shop/orders/lookup`. Le résultat affiche le statut (en attente de paiement, payée, expirée), les lignes figées et les totaux. Un numéro inconnu et un email erroné affichent le même message, comme côté serveur.

## Parcours de commande
`/panier` (lignes, devis serveur, formulaire email et adresse) crée la commande (`POST /api/shop/orders`, clé d'idempotence par contenu) puis ouvre `/paiement/[orderId]` : écran de paiement simulé **sans champ de carte**, deux boutons (paiement réussi, refus) qui envoient une méthode de test à `POST /api/shop/orders/{id}/pay/confirm`. Un refus permet un nouvel essai; un succès vide le panier et mène à `/success?commande=BC-…` (le numéro n'est affiché que s'il a le format d'un numéro de commande). Stripe n'existe plus dans le front : aucune clé de paiement n'est requise au build ni à l'exécution.

## Organisation
`src/app` (routes), `src/components`, `src/context` (panier), `src/lib` (utilitaires métier), `src/types`.

## Qualité
`npm run quality` (ESLint sans warning, Prettier, `tsc`), `npm run test:coverage` (Vitest, seuil 80 %). Tests colocalisés dans `__tests__/`.

## Configuration
Variables d'environnement décrites dans `apps/frontend/.env.example`; aucune clé privée n'est exposée au navigateur.

## Design
Palette : vert forêt `#1E3A2F`, orange bivouac `#E05638`, neutres pierre et sable. Badges techniques sur les produits (poids, imperméabilité, température de confort, matériau). Conception mobile first.

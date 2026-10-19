# Suivi du Projet — Journal de Bord (brain.md)

**Dernière mise à jour :** 19 Octobre 2026  
**Auteur / Contexte :** Cluster Proxmox (accès MPSRM2), Gestion des VMs, et Nouvelle Boutique E-Commerce "Basecamp Outdoor".

---

## 1. Proxmox VE — Configuration des accès Étudiants (Pool MPSRM2)

### Objectifs & Réalisations
- **Isolation stricte** : Les étudiants ne voient **que** leur pool et leurs VMs.
- **Utilisateurs créés (`@pve`)** : `Samuel.R`, `Remi.L`, `Remi.T`, `Theo.T`, `Samuel.Q`.
- **Mot de passe initial** : Défini via vault / politique interne `[MOT_DE_PASSE_PROJET]`.
- **Groupe** : `grp-mpsrm2`
- **Permissions appliquées (ACL)** :
  - `/pool/MPSRM2` $\rightarrow$ `Administrator` (gestion totale dans le pool).
  - `/pool` $\rightarrow$ `PVEPoolUser` (visibilité du pool dans les listes déroulantes).
  - `/storage/local-zfs` & `/storage/local` $\rightarrow$ `PVEDatastoreUser` (disques et images ISO).
  - `/sdn` $\rightarrow$ `PVESDNUser` (cartes réseaux et zones SDN).
  - `/nodes` $\rightarrow$ `VM_CREATOR`, `PVEVMUser`, `BridgeViewer` (visibilité `vmbr0` sans fuite sur les autres VMs).
  - `/` $\rightarrow$ `VM_CREATOR`, `PVEVMUser` avec `--propagate 0`.
- **VM 104 (`docker-ha`)** intégrée au pool `MPSRM2`.
- **Mode d'affichage recommandé** : Vue par pool (**Pool View**) en haut à gauche.

---

## 2. Découverte & Connexion sur la Machine Docker (`192.168.1.103`)

- **Hôte :** `anto-docker` (`192.168.1.103`, VM 103 `HERMES`)
- **Accès SSH :** Compte `anto` (authentification sécurisée par mot de passe / clé).
- **Résolution Login Fire OS (`fire-os.tempulse.fr`) :**
  - **Identifiant correct :** `anto` *(et non `admin`)*
  - **Mot de passe :** Configuré dans l'environnement du conteneur `[REDACTED_PASSWORD]`.
  - Panneau géré par le conteneur `agent-dashboard` (`uvicorn main:app`, port 8090).

---

## 3. Analyse de la Boutique E-commerce Template (`~/caniventure`)

- **Conteneur :** `caniventure-shop` (port 3000)
- **Stack technique :**
  - **Framework :** Next.js 14 (`^14.2.35`, App Router)
  - **UI & Style :** React 18, Tailwind CSS (`3.4`), Lucide React, Framer Motion (`14.1`)
  - **Paiements :** Stripe SDK (`^23.0.0`)
  - **Emails transactionnels :** Resend (`^6.32.1`)
  - **Validation & Sécurité :** Zod (`^4.6.6`), Next-Auth (`^4.24.15`)
- **Architecture App Router :**
  - `/api` : routes Stripe webhooks, checkout, auth
  - `/compte`, `/connexion`, `/suivi` (suivi de commandes)
  - `/cgv`, `/confidentialite`, `/mentions-legales`
  - `/success` (page de remerciement post-paiement)
  - `/src/components`, `/src/context` (panier, etc.), `/src/lib`, `/src/types`

---

## 4. Inventaire des 55 Skills sur le Serveur Hermes (`192.168.1.104:8091`)

Le serveur de skills est actif (`{"ok": true, "skill_count": 55}`). Les compétences exploitées :

### Sécurité & Audit
- `sec-code-owasp` : Revue de code défensif, audit SAST, validation d'entrées Zod, vérification des webhooks Stripe.
- `sec-web-audit` : Scanner de surface d'attaque web, en-têtes HTTP de sécurité (CSP, HSTS, CORS).
- `sec-infra-hardening` : Durcissement des conteneurs Docker (non-root, isolation).
- `owasp-web-security-auditor` : Audit selon l'OWASP Top 10.

### Marketing, Stratégie & CRO
- `cro-friction-audit` : Diagnostic des frictions de conversion, optimisation du panier et du checkout.
- `seo-technical-geo` & `technical-seo-auditor` : Balisage Schema.org (`Product`, `Offer`), Core Web Vitals, référencement IA (GEO/AEO).
- `founder-offer`, `founder-brand`, `founder-pricing`, `founder-marketing`, `founder-launch` : Positionnement d'offre et stratégie commerciale.

### UX & Design
- `design-system-tokens` : Architecture de tokens, grille modulaire 4px/8px Tailwind.
- `micro-interactions-motion` : Animations d'interface et états de transition fluides.
- `ux-heuristics-evaluator` : Évaluation ergonomique selon les 10 principes de Nielsen Norman.
- `ux-writing-microcopy` : Micro-copie des boutons, messages d'erreurs rassurants.
- `wcag-accessibility-auditor` : Accessibilité WCAG 2.2 AA.

---

## 5. Déblocage du Rate-Limit Fire OS

- **Problème :** Blocage 429 *"Trop de tentatives, réessaie dans 15 minutes"* suite à la saisie de l'identifiant erroné `antony`.
- **Cause :** L'identifiant réel configuré est **`anto`** (et non `antony`).
- **Résolution :** Redémarrage à chaud du conteneur `agent-dashboard` sur `192.168.1.103` (`docker restart agent-dashboard`), ce qui a vidé le dictionnaire mémoire des tentatives échouées (`_FAILS`).
- **Statut :** Accès rétabli avec succès.

---

## 6. Installation des Skills en Local (Antigravity & Claude Code)

- **Dossiers configurés :**
  - Antigravity : `.agents/skills/`
  - Claude Code : `.claude/skills/`
- **11 Skills clés extraits et installés avec frontmatter YAML :**
  1. `sec-code-owasp` (sécurité code & Zod)
  2. `sec-web-audit` (headers CSP/HSTS & audit web)
  3. `owasp-web-security-auditor` (audit OWASP Top 10, remédiation injections, XSS, SSRF)
  4. `sec-infra-hardening` (durcissement conteneurs Docker & reverse proxy)
  5. `stripe-checkout-billing` (paiements Stripe et validation webhooks)
  6. `seo-technical-geo` (Schema.org JSON-LD & référencement IA)
  7. `technical-seo-auditor` (audit technique SEO, Core Web Vitals, sitemaps)
  8. `cro-friction-audit` (optimisation conversion et tunnel d'achat)
  9. `ux-heuristics-evaluator` (heuristiques Nielsen Norman)
  10. `design-system-tokens` (système de tokens Tailwind)
  11. `micro-interactions-motion` (animations Framer Motion)
- **Fichier de configuration synchronisé :** [CLAUDE.md](file:///c:/Users/Antony/Desktop/Workshop%20m2/CLAUDE.md).

---

## 7. Gestion Système : Utilisateur Debian `epsi` (anto-docker)

- Création du compte utilisateur `epsi` sur la VM `anto-docker` (`adduser epsi`).
- Attribution des privilèges d'administration : `usermod -aG sudo epsi`.
- Application des droits effective via reconnexion SSH ou `newgrp sudo`.

---

## 8. Livraison & Validation Scaffold "Basecamp Outdoor" (Claude Code)

Claude Code a terminé et validé l'adaptation complète du template e-commerce :

1. **Stack & Build :**
   - Next.js 14 (App Router) + TypeScript + Tailwind + Stripe + Resend + Zod + Framer Motion.
   - Build validé sans erreur (`next build` ✓).
   - Serveur de dev validé (toutes les pages en HTTP 200).
2. **Direction Artistique (`tailwind.config.ts`) :**
   - Vert forêt `#1E3A2F`, Orange bivouac `#E05638`, Granit `#181D1A`, Sable `#F5F2EB`.
   - Système de tokens 4px/8px et échelle typographique robuste.
3. **Catalogue Produit (`src/lib/products.ts`) :**
   - 10 fiches produits réelles (tentes de bivouac, sacs de couchage, réchauds titane, sacs à dos).
   - Badges techniques en place : poids en g, imperméabilité Schmerber mm, température confort, saisons.
4. **UX / CRO & Conversion :**
   - Fiche produit optimisée au-dessus de la ligne de flottaison.
   - Bouton d'ajout au panier sticky sur mobile.
   - Panier tiroir (Slide-over Cart) avec barre de livraison gratuite animée.
   - Bandeau de réassurance : expédition 24/48h, garantie aventure/déchirure, retours gratuits 30 jours.
5. **SEO & Moteurs Génératifs (GEO/AEO) :**
   - Balisage Schema.org complet : `Product`, `Offer`, `AggregateRating`, `BreadcrumbList`.
   - Balises OpenGraph et meta descriptives riches.
   - Sitemap et robots dynamiques.
6. **Sécurité Défensive :**
   - En-têtes HTTP de sécurité configurés et testés (CSP, HSTS, X-Frame-Options).
   - Schémas Zod stricts (`.strict()`) sur `/api/checkout` (injections de prix bloquées).
   - Vérification cryptographique des webhooks Stripe (`stripe.webhooks.constructEvent`).
   - Rate-limiting et validation des variables d'environnement.
7. **Hygiène de Sécurité :**
   - Nettoyage des mots de passe en clair dans `brain.md` (effectué).

---

## 9. Résultats de l'Audit SEO & du Pentest Défensif (Claude Code)

### A. Optimisations SEO, Structure Hn & Données Marchandes (GEO/AEO)
1. **Hiérarchie Hn corrigée :**
   - Suppression du saut `<h1>` $\rightarrow$ `<h3>` sur les pages catégories (insertion d'un `<h2>` sémantique de contexte).
   - Remplacement des `<h3>` du `Footer.tsx` par des `<h2>` pour préserver l'arborescence sur les pages simples (`/cgv`, `/contact`, `/suivi`).
2. **Métadonnées & Descriptions :**
   - Métadescription d'accueil raccourcie à 144 caractères (norme 140-160).
   - Enrichissement dynamique des descriptions produits et catégories via `src/lib/seo.ts` (description + specs techniques + réassurance).
   - Ajout systématique des URLs canoniques et balises OpenGraph sur toutes les pages institutionnelles.
3. **Rich Snippets Google & Moteurs IA :**
   - Données structurées JSON-LD `Product` enrichies avec `sku`, `shippingDetails` et `hasMerchantReturnPolicy`.

### B. Pentest Défensif & Remédiations de Sécurité
Cinq tests d'intrusion défensifs ont été exécutés, révélant et corrigeant **2 vulnérabilités réelles** :

| Cible / Vecteur | Comportement initial | Vulnérabilité / Risque | Remédiation appliquée | Résultat après patch |
|---|---|---|---|---|
| **Falsification de panier** (`productId` inconnu) | Exception JS non catchée dans `.map()` $\rightarrow$ HTTP 500 brut | Fuite d'informations d'erreur serveur (CWE-209) | Vérification d'existence avant construction des items + `try/catch` global | **HTTP 400 Propre** avec message d'erreur générique |
| **Contournement CORS / CSRF** | Requête POST acceptée sans restriction de type | Envoi de JSON malveillant avec `Content-Type: text/plain` (contournement preflight) | Validation stricte du header `Content-Type: application/json` | **HTTP 415 Unsupported Media Type** bloquant l'attaque |
| **Réflexion d'input (XSS)** | Message d'erreur renvoyait le `productId` brut | Mauvaise pratique OWASP (risque d'injection réfléchie) | Suppression de la réflexion des données utilisateur | Message neutre assaini |
| **Webhook Stripe** | Test sans en-tête `stripe-signature` | Risque d'appel frauduleux de confirmation de commande | Vérification cryptographique native `stripe.webhooks.constructEvent` | **HTTP 400 Bad Request** immédiat |
| **Résilience Webhook / Emails** | Envoi d'email Resend pouvait lever une exception | Risque de retries infinis par Stripe en cas de panne Resend | Isolation de l'envoi d'email dans un `try/catch` dédié | Retour HTTP 200 garanti à Stripe une fois le paiement loggué |
| **Rate-Limiting `/api/checkout`** | Test de spam (15 requêtes rapides) | Risque de déni de service / épuisement d'API | Seuil fixé à 10 req/min avec header `Retry-After: 40` | **HTTP 429 Too Many Requests** actif dès la 9e requête |
| **En-têtes HTTP & Clickjacking** | Test CSP, HSTS, X-Frame-Options | Risque de détournement de clic (Clickjacking) | `X-Frame-Options: DENY`, `nosniff`, `CSP` strict avec Stripe | **Headers conformes et vérifiés** |

### C. Conteneurisation & Durcissement Infrastructure (`sec-infra-hardening`)
- Génération d'un **`Dockerfile` multi-stage** optimisé pour la production (`node:20-alpine`).
- Activation de l'exécution **non-root** obligatoire : création d'un utilisateur système `nextjs` (UID 1001) sans privilèges.
- Configuration `output: 'standalone'` dans `next.config.mjs` pour un poids d'image Docker minimal.
- Création d'un `.dockerignore` strict (exclusion de `node_modules`, `.env`, `.git`, `brain.md`).
- Validation finale complète : `next build` réussi avec 28 pages statiques/dynamiques pré-générées.

---

## 10. Déploiement en Production & Mise en Ligne Réussie (basecamp.tempulse.fr)

- **DNS Cloudflare :** CNAME `basecamp.tempulse.fr` $\rightarrow$ `tempulse.fr` (Proxy Cloudflare activé ☁️).
- **Reverse-Proxy Traefik v3 :** Interception du nom de domaine `basecamp.tempulse.fr` sur le réseau `web`, redirection HTTP $\rightarrow$ HTTPS automatique.
- **Conteneur Docker :** `basecamp-shop` actif sur `192.168.1.103` (`anto-docker`), exécuté sous l'utilisateur non-root `nextjs`.
- **Statut Live :** **HTTP 200 OK** vérifié en direct via `https://basecamp.tempulse.fr`.
- **En-têtes de sécurité actifs :** CSP, HSTS, X-Frame-Options: DENY, Referrer-Policy, nosniff.

---

## 11. Prochaines Étapes
- [ ] Connecter les vraies clés Stripe (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`) et Resend (`RESEND_API_KEY`) dans `~/basecamp-outdoor/docker-compose.yml`.
- [ ] Personnaliser les images de produits et textes marketing selon vos préférences.

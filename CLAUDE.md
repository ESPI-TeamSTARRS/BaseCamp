# Claude Code Guidelines & Skills Reference — E-Commerce Template & New Niche

Ce projet utilise une stack **Next.js 14 (App Router) + TypeScript + Tailwind CSS 3.4 + Framer Motion + Stripe + Resend + Zod**.
Des **skills spécialisés** sont installés dans le dossier `.claude/skills/` pour guider chaque aspect du développement.

---

## 1. Skills Spécialisés Disponibles (`.claude/skills/`)

Avant d'écrire ou modifier du code, consulte systématiquement les instructions des skills correspondants :

### 🛡️ Sécurité, Pentest Défensif & Conformité
- [`.claude/skills/sec-code-owasp/SKILL.md`](file:///.claude/skills/sec-code-owasp/SKILL.md) : Validation stricte des schémas d'entrée Zod (`.strict()`), vérification cryptographique obligatoire des signatures de webhooks Stripe, assainissement des messages d'erreur.
- [`.claude/skills/sec-web-audit/SKILL.md`](file:///.claude/skills/sec-web-audit/SKILL.md) : En-têtes HTTP de sécurité (CSP, HSTS, X-Content-Type-Options, Referrer-Policy), gestion stricte des cookies de session (`SameSite=Strict`, `HttpOnly`, `Secure`).
- [`.claude/skills/owasp-web-security-auditor/SKILL.md`](file:///.claude/skills/owasp-web-security-auditor/SKILL.md) : Audit OWASP Top 10 web et API, détection et remédiation des injections, XSS, bris d'authentification et failles SSRF.
- [`.claude/skills/sec-infra-hardening/SKILL.md`](file:///.claude/skills/sec-infra-hardening/SKILL.md) : Durcissement des conteneurs Docker (non-root, filesystem en lecture seule quand applicable, drop capabilities).

### 💳 Paiement & Tunnel d'Achat
- [`.claude/skills/stripe-checkout-billing/SKILL.md`](file:///.claude/skills/stripe-checkout-billing/SKILL.md) : Configuration des Sessions Stripe Checkout, gestion idempotente des événements webhooks (`checkout.session.completed`), politique de gestion des échecs de paiement et redirection `/success`.

### 📈 Marketing, SEO & Conversion (CRO)
- [`.claude/skills/seo-technical-geo/SKILL.md`](file:///.claude/skills/seo-technical-geo/SKILL.md) : Balisage sémantique Schema.org (`Product`, `Offer`, `BreadcrumbList`), OpenGraph, balises meta canoniques, sitemap dynamique et optimisation pour les moteurs IA (GEO/AEO).
- [`.claude/skills/technical-seo-auditor/SKILL.md`](file:///.claude/skills/technical-seo-auditor/SKILL.md) : Audit technique SEO complet, Core Web Vitals (LCP, INP, CLS), hiérarchie Hn stricte, balisage robot et maillage interne.
- [`.claude/skills/cro-friction-audit/SKILL.md`](file:///.claude/skills/cro-friction-audit/SKILL.md) : Élimination des points de friction dans le tunnel d'achat, optimisation de la page produit (au-dessus de la ligne de flottaison), panier latéral sticky, réassurance et call-to-action percutants.

### 🎨 UX, Design & Accessibilité
- [`.claude/skills/ux-heuristics-evaluator/SKILL.md`](file:///.claude/skills/ux-heuristics-evaluator/SKILL.md) : Respect des 10 principes de Nielsen Norman, lois de Fitts et Hick pour la hiérarchie visuelle et la navigation.
- [`.claude/skills/design-system-tokens/SKILL.md`](file:///.claude/skills/design-system-tokens/SKILL.md) : Système modulaire de tokens Tailwind (espacements 4px/8px, palette accessible, typographie fluide).
- [`.claude/skills/micro-interactions-motion/SKILL.md`](file:///.claude/skills/micro-interactions-motion/SKILL.md) : Micro-animations Framer Motion discrètes (hover, ouverture du panier, loaders réactifs).

---

## 2. Niche & Direction Artistique (DA) : Basecamp Outdoor

Le template d'origine (`caniventure`) doit être intégralement rethémé vers une boutique de **matériel outdoor, bivouac et grande randonnée**.

### 🌲 Identité & Ambiance Visuelle
- **Inspirations de marque :** Basecamp, Patagonia, Arc'teryx, Snow Peak, Fjällräven.
- **Palette de couleurs :**
  - Primaire : Vert forêt / Pin profond (`#1E3A2F` ou `#132E22`)
  - Accent / CTA : Orange bivouac / Terracotta brûlée (`#E05638` ou `#C84B31`)
  - Neutres : Pierre / Granit foncé (`#181D1A`, `#222925`), Sable / Écru (`#F5F2EB`, `#E8E2D5`)
- **Typographie & Style :** Moderne, robuste, aventure (Inter / Geist Sans avec accents typographiques outdoor).
- **Badges techniques indispensables :** Poids ultralight (ex: `850g`), imperméabilité (ex: `3 000mm Schmerber`), indice de température (ex: `-5°C confort`), matériaux durables (ex: `Nylon Ripstop 20D`).

### 🎒 Catalogue Produits Cible (Bivouac & Trek)
1. **Tentes de bivouac & abris ultralégers** (1P/2P, autoportantes, 3 et 4 saisons).
2. **Sacs de couchage & matelas gonflables isolants** (plume d'oie déperlante, R-value élevée).
3. **Sacs à dos de grande randonnée** (45L à 65L avec armature ergonomique).
4. **Matériel de camp & cuisine** (réchauds titane, popotes ultralight, filtres à eau portables).
5. **Accessoires de sécurité & orientation** (lampes frontales rechargeables, boussoles, trousses de secours outdoor).

---

## 3. Règles Fondamentales de Développement
1. **Validation Systématique :** Aucune route API ne doit traiter de données sans validation `zod.safeParse()`.
2. **Secrets & Environnement :** Aucune clé privée ou token en dur dans le code. Toujours utiliser les variables d'environnement (`process.env.*`) avec validation dans un fichier de config.
3. **Composants Réutilisables :** Suivre l'architecture Next.js App Router (`src/components/`, `src/app/`, `src/lib/`, `src/context/`).
4. **Mobile First :** Chaque interface doit être parfaitement réactive et testée pour les écrans mobiles en priorité (bivouac = consultation sur smartphone en conditions de mobilité).

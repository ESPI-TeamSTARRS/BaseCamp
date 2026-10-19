---
name: design-system-tokens
description: Architecture et standardisation de Design Tokens : grille d'espacement modulaire 4px/8px, échelle typographique, palettes sémantiques sombres/claires et élévations d'ombres.
category: creative
---

# Design System Tokens Architecture

Système de jetons de design (Tokens) pour assurer la cohérence esthétique, la maintenabilité et la lisibilité du code CSS.

## 1. Hiérarchie des Tokens à 3 Niveaux

1. **Tokens Globaux** : Valeurs primitives brutes (ex: `--palette-blue-500: #3b82f6;`).
2. **Tokens Sémantiques** : Rôle et intention fonctionnelle (ex: `--color-primary-active: var(--palette-blue-500);`).
3. **Tokens de Composants** : Attribués à un élément précis (ex: `--btn-primary-bg: var(--color-primary-active);`).

## 2. Grille d'Espacement Modulaire (Base 4px / Grille 8px)

Bannir les valeurs arbitraires au pixel près (comme `13px` ou `27px`). Utiliser une échelle constante :
```css
:root {
  --space-1:  4px;   /* Micro ajustements, gaps d'icônes */
  --space-2:  8px;   /* Marges internes serrées, tags */
  --space-3: 12px;   /* Padding de boutons standards */
  --space-4: 16px;   /* Padding de cartes compactes, espacement de champs */
  --space-5: 20px;   /* Marges modérées */
  --space-6: 24px;   /* Padding de cartes principales, sections */
  --space-8: 32px;   /* Séparation de blocs de contenu */
  --space-12: 48px;  /* Marges de conteneurs et sections */
  --space-16: 64px;  /* Espacements majeurs de page */
}
```

## 3. Typographie & Échelle Modulaire

```css
:root {
  --font-family-sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-family-mono: 'JetBrains Mono', monospace;

  --text-xs:   0.75rem;   /* 12px - Badges, métadonnées */
  --text-sm:   0.875rem;  /* 14px - Textes secondaires, inputs */
  --text-base: 1.0rem;    /* 16px - Corps de texte principal */
  --text-lg:   1.125rem;  /* 18px - Sous-titres de cartes */
  --text-xl:   1.25rem;   /* 20px - Titres de cartes */
  --text-2xl:  1.5rem;    /* 24px - Titres de sections (h2) */
  --text-3xl:  1.875rem;  /* 30px - Titres principaux (h1) */
}
```

## 4. Palette Sémantique Dark Mode & Élévations

```css
:root {
  /* Surfaces */
  --surface-canvas:  #08090d;
  --surface-card:    #0f121a;
  --surface-elevated: #161b26;
  --surface-hover:   #1d2433;

  /* Bordures */
  --border-subtle:   rgba(255, 255, 255, 0.08);
  --border-active:   rgba(99, 102, 241, 0.4);

  /* Ombres en multi-couches */
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3), 0 0 1px rgba(255, 255, 255, 0.05) inset;
  --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.4), 0 0 1px rgba(255, 255, 255, 0.08) inset;
  --shadow-lg: 0 12px 32px rgba(0, 0, 0, 0.5), 0 0 1px rgba(255, 255, 255, 0.1) inset;
}
```

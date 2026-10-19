---
name: technical-seo-auditor
description: Audit technique SEO et performance web : Core Web Vitals (LCP, INP, CLS), balisage sémantique, métadonnées OpenGraph, Schema.org JSON-LD et sitemaps.
category: productivity
---

# Technical SEO & Web Vitals Auditor

Checklist et implémentations pour maximiser la visibilité dans les moteurs de recherche et l'expérience utilisateur.

## 1. Balisage HTML Sémantique & Structure

- **Un seul `<h1>` par page** décrivant précisément le sujet unique.
- Hiérarchie stricte sans saut de niveau : `<h1>` > `<h2>` > `<h3>`.
- Métadonnées indispensables dans `<head>` :
```html
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Titre Unique et Descriptif | Marque (50-60 car)</title>
<meta name="description" content="Description engageante avec mots-clés naturels entre 140 et 160 caractères.">
<link rel="canonical" href="https://domaine.fr/url-propre">
```

## 2. OpenGraph & Twitter Cards

```html
<meta property="og:type" content="website">
<meta property="og:url" content="https://domaine.fr/page">
<meta property="og:title" content="Titre de la page">
<meta property="og:description" content="Description engageante">
<meta property="og:image" content="https://domaine.fr/og-image.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">

<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Titre de la page">
<meta name="twitter:description" content="Description engageante">
<meta name="twitter:image" content="https://domaine.fr/og-image.jpg">
```

## 3. Données Structurées Schema.org (JSON-LD)

```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "Fire OS",
  "applicationCategory": "BusinessApplication",
  "operatingSystem": "Web",
  "description": "Plateforme d'orchestration multi-agents et mémoire centrale.",
  "offers": {
    "@type": "Offer",
    "price": "0",
    "priceCurrency": "EUR"
  }
}
</script>
```

## 4. Optimisation des Core Web Vitals

- **LCP (Largest Contentful Paint < 2.5s)** : Précharger l'image héroïque via `<link rel="preload" as="image" href="...">` et éviter le lazy-loading sur les images au-dessus du pli.
- **CLS (Cumulative Layout Shift < 0.1)** : Définir explicitement les attributs `width` et `height` (ou `aspect-ratio` en CSS) sur toutes les balises `<img>`, `<video>` et `<iframe>`.
- **INP (Interaction to Next Paint < 200ms)** : Découper les tâches JavaScript longues en micro-tâches avec `setTimeout` ou `scheduler.yield()`.

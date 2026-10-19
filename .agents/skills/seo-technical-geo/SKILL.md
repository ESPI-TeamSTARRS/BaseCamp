---
name: seo-technical-geo
description: Master Technical SEO, Schema.org JSON-LD, Core Web Vitals, and GEO/AEO (Generative Engine Optimization) auditor for Next.js, e-commerce, and modern web applications.
category: marketing
---

# Technical SEO, Rich Snippets & GEO/AEO Master Skill (seo-technical-geo)

Guide complet d'optimisation pour le référencement naturel traditionnel (Google, Bing) et le référencement IA (ChatGPT Search, Perplexity, Claude, Google AI Overviews).

## 1. Architecture des Métadonnées Next.js (App Router)

### A. Root Layout (`src/app/layout.tsx`)
Obligation de définir `metadataBase` pour la résolution des URLs absolues et des balises canoniques :

```typescript
export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || 'https://caniventure.tempulse.fr'),
  title: {
    default: 'CaniVenture — Housse de Protection Intégrale Voiture pour Chien',
    template: '%s | CaniVenture',
  },
  description: 'Protégez vos sièges auto des poils, boue et griffes avec le Pack Sérénité Auto CaniVenture. Housse 600D étanche + ceinture sécurité offerte.',
  alternates: {
    canonical: '/',
  },
  openGraph: {
    title: 'CaniVenture — Voyagez serein avec votre chien',
    description: 'La housse de siège auto intégrale 600D imperméable et indéchirable.',
    url: 'https://caniventure.tempulse.fr',
    siteName: 'CaniVenture',
    locale: 'fr_FR',
    type: 'website',
    images: [
      {
        url: '/images/og-image.jpg',
        width: 1200,
        height: 630,
        alt: 'Pack Sérénité Auto CaniVenture',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'CaniVenture — Pack Sérénité Auto',
    description: 'Protection intégrale pour vos sièges auto de chien.',
    images: ['/images/og-image.jpg'],
  },
};
```

---

## 2. Données Structurées Schema.org JSON-LD (Rich Snippets)

Les microdonnées JSON-LD permettent d'obtenir les étoiles d'avis, les prix, les stocks et les accordéons FAQ directement dans les résultats Google.

### A. Schéma E-Commerce Produit (`Product` + `Offer`)
À insérer dans la page produit / landing :

```html
<script type="application/ld+json" dangerouslySetInnerHTML={{
  __html: JSON.stringify({
    "@context": "https://schema.org/",
    "@type": "Product",
    "name": "Pack Sérénité Auto CaniVenture",
    "image": ["https://caniventure.tempulse.fr/images/pack-hero.jpg"],
    "description": "Housse de protection intégrale pour banquette arrière de voiture, Oxford 600D imperméable avec ceinture de sécurité anti-choc.",
    "brand": {
      "@type": "Brand",
      "name": "CaniVenture"
    },
    "offers": {
      "@type": "Offer",
      "url": "https://caniventure.tempulse.fr",
      "priceCurrency": "EUR",
      "price": "69.90",
      "priceValidUntil": "2027-12-31",
      "availability": "https://schema.org/InStock",
      "shippingDetails": {
        "@type": "OfferShippingDetails",
        "shippingRate": {
          "@type": "MonetaryAmount",
          "value": "0.00",
          "currency": "EUR"
        },
        "deliveryTime": {
          "@type": "ShippingDeliveryTime",
          "businessDays": {
            "@type": "OpeningHoursSpecification",
            "dayOfWeek

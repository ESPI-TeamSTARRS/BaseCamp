import type { Product } from '@/types/product';

export const products: Product[] = [
  {
    id: 'tente-ultralight-2p',
    slug: 'tente-bivouac-ultralight-2p',
    name: 'Tente Bivouac Ultralight 2P',
    category: 'tentes',
    priceEur: 329,
    compareAtPriceEur: 389,
    shortDescription:
      'Abri autoportant 2 places, 3 saisons, conçu pour la grande randonnée en autonomie.',
    description:
      "Notre tente de bivouac ultralight combine une armature en aluminium 7001 et un double toit en Nylon Ripstop 20D siliconé pour une résistance maximale au vent sans compromis sur le poids. Montage rapide à deux arceaux croisés, ventilation double flux anti-condensation et abside généreuse pour le stockage du matériel.",
    images: ['/images/products/tente-ultralight-2p-1.jpg', '/images/products/tente-ultralight-2p-2.jpg'],
    specs: {
      weightGrams: 1480,
      waterproofingMm: 3000,
      comfortTempC: -5,
      seasons: 3,
      capacityLiters: undefined,
      material: 'Nylon Ripstop 20D',
    },
    stock: 24,
    ratingValue: 4.8,
    ratingCount: 132,
  },
  {
    id: 'sac-couchage-plume-900',
    slug: 'sac-de-couchage-duvet-900',
    name: 'Sac de Couchage Duvet 900',
    category: 'couchage',
    priceEur: 279,
    shortDescription: 'Duvet d\'oie déperlant 900 cuin, confort -9°C, compressible à l\'extrême.',
    description:
      "Garnissage en duvet d'oie déperlant certifié RDS (900 cuin de gonflant) pour un rapport chaleur/poids inégalé. Le traitement déperlant conserve le pouvoir isolant même en cas d'humidité légère — indispensable en bivouac. Capuche ajustable, collerette anti-déperdition et pochette de compression incluse.",
    images: ['/images/products/sac-couchage-duvet-900-1.jpg'],
    specs: {
      weightGrams: 850,
      comfortTempC: -9,
      seasons: 3,
      material: "Duvet d'oie 900 cuin déperlant",
    },
    stock: 18,
    ratingValue: 4.9,
    ratingCount: 87,
  },
  {
    id: 'matelas-isolant-rvalue7',
    slug: 'matelas-gonflable-isolant-r7',
    name: 'Matelas Gonflable Isolant R7',
    category: 'couchage',
    priceEur: 149,
    shortDescription: 'R-value 7.0, isolation hiver, gonflage rapide par pompe intégrée.',
    description:
      'Matelas gonflable à chambres horizontales avec isolation multicouche réfléchissante (R-value 7.0), conçu pour les bivouacs hivernaux. Pompe à sac intégrée pour un gonflage sans effort, valve double action pour un dégonflage instantané.',
    images: ['/images/products/matelas-r7-1.jpg'],
    specs: {
      weightGrams: 620,
      comfortTempC: -15,
      seasons: 4,
      material: 'Nylon 40D + isolation TPU réfléchissante',
    },
    stock: 31,
    ratingValue: 4.7,
    ratingCount: 64,
  },
  {
    id: 'sac-a-dos-trek-55l',
    slug: 'sac-a-dos-randonnee-55l',
    name: 'Sac à Dos Trek 55L',
    category: 'sacs-a-dos',
    priceEur: 219,
    shortDescription: 'Armature ergonomique ventilée, portage longue distance, 55 litres.',
    description:
      "Architecture à armature aluminium et dos ventilé en treillis 3D pour une circulation d'air optimale sur les longues distances. Système de portage ajustable sur 15cm, ceinture lombaire moulée et compartiment dédié pour poche à eau. Compatible fixation tente et matelas externe.",
    images: ['/images/products/sac-a-dos-55l-1.jpg'],
    specs: {
      weightGrams: 1620,
      capacityLiters: 55,
      material: 'Nylon 420D Ripstop',
    },
    stock: 15,
    ratingValue: 4.6,
    ratingCount: 103,
  },
  {
    id: 'rechaud-titane-ultralight',
    slug: 'rechaud-titane-ultralight',
    name: 'Réchaud Titane Ultralight',
    category: 'cuisine',
    priceEur: 59,
    shortDescription: 'Réchaud à gaz pliable 25g, puissance 2800W, piézo intégré.',
    description:
      'Réchaud en titane de 25 grammes seulement, puissance de 2800W pour une ébullition rapide même en altitude. Pieds pliables grand angle pour une stabilité optimale, allumage piézoélectrique intégré, livré avec étui de rangement.',
    images: ['/images/products/rechaud-titane-1.jpg'],
    specs: {
      weightGrams: 25,
      material: 'Titane grade 5',
    },
    stock: 42,
    ratingValue: 4.8,
    ratingCount: 211,
  },
  {
    id: 'popote-titane-900ml',
    slug: 'popote-titane-900ml',
    name: 'Popote Titane 900ml',
    category: 'cuisine',
    priceEur: 39,
    shortDescription: 'Gamelle titane ultralégère avec couvercle poêle et poignées pliantes.',
    description:
      'Popote en titane pur de 900ml, idéale pour les expéditions solo ou duo. Couvercle réversible utilisable comme poêle, poignées pliantes anti-brûlure, sac de transport en mesh inclus.',
    images: ['/images/products/popote-titane-1.jpg'],
    specs: {
      weightGrams: 142,
      material: 'Titane pur',
    },
    stock: 56,
    ratingValue: 4.7,
    ratingCount: 98,
  },
  {
    id: 'filtre-eau-portable',
    slug: 'filtre-a-eau-portable',
    name: 'Filtre à Eau Portable',
    category: 'cuisine',
    priceEur: 34,
    shortDescription: 'Filtration 0.1 micron, élimine 99.99% des bactéries, 4000L de capacité.',
    description:
      'Filtre à paille ultra-compact avec membrane à fibres creuses 0.1 micron, éliminant 99.99% des bactéries et protozoaires. Capacité de filtration de 4000 litres sans entretien, poids plume pour l\'autonomie en bivouac.',
    images: ['/images/products/filtre-eau-1.jpg'],
    specs: {
      weightGrams: 58,
      material: 'Fibres creuses + ABS',
    },
    stock: 67,
    ratingValue: 4.6,
    ratingCount: 145,
  },
  {
    id: 'lampe-frontale-rechargeable',
    slug: 'lampe-frontale-rechargeable',
    name: 'Lampe Frontale Rechargeable',
    category: 'securite',
    priceEur: 44,
    shortDescription: '600 lumens, USB-C, étanche IPX6, autonomie 40h en mode éco.',
    description:
      'Lampe frontale rechargeable USB-C offrant jusqu\'à 600 lumens en pleine puissance et 40h d\'autonomie en mode éco. Certification IPX6 résistante aux intempéries, éclairage rouge nocturne pour préserver la vision nocturne au bivouac.',
    images: ['/images/products/lampe-frontale-1.jpg'],
    specs: {
      weightGrams: 92,
      material: 'ABS + silicone',
    },
    stock: 38,
    ratingValue: 4.7,
    ratingCount: 176,
  },
  {
    id: 'boussole-orientation-pro',
    slug: 'boussole-orientation-pro',
    name: 'Boussole d\'Orientation Pro',
    category: 'securite',
    priceEur: 29,
    shortDescription: 'Boussole de précision avec clinomètre, loupe et viseur de visée.',
    description:
      'Boussole professionnelle à visée miroir avec clinomètre intégré pour l\'estimation de pente, loupe de lecture de carte et liquide d\'amortissement anti-vibration pour une lecture stable en conditions difficiles.',
    images: ['/images/products/boussole-pro-1.jpg'],
    specs: {
      weightGrams: 65,
      material: 'ABS renforcé + verre minéral',
    },
    stock: 29,
    ratingValue: 4.5,
    ratingCount: 52,
  },
];

export function getProductBySlug(slug: string): Product | undefined {
  return products.find((p) => p.slug === slug);
}

export function getProductsByCategory(category: Product['category']): Product[] {
  return products.filter((p) => p.category === category);
}

export const categoryLabels: Record<Product['category'], string> = {
  tentes: 'Tentes & Abris',
  couchage: 'Couchage',
  'sacs-a-dos': 'Sacs à Dos',
  cuisine: 'Camp & Cuisine',
  securite: 'Sécurité & Orientation',
};

export type ProductCategory = 'tentes' | 'couchage' | 'sacs-a-dos' | 'cuisine' | 'securite';

export type Availability = 'in_stock' | 'low_stock' | 'out_of_stock';

export interface TechSpecs {
  weightGrams?: number;
  waterproofingMm?: number;
  comfortTempC?: number;
  seasons?: 1 | 2 | 3 | 4;
  capacityLiters?: number;
  material?: string;
}

/** Produit tel que renvoyé par l'API shop (prix converti des centimes en euros). */
export interface Product {
  id: string;
  slug: string;
  name: string;
  category: ProductCategory;
  priceEur: number;
  compareAtPriceEur?: number;
  shortDescription: string;
  description: string;
  images: string[];
  specs: TechSpecs;
  availability: Availability;
  ratingValue: number;
  ratingCount: number;
}

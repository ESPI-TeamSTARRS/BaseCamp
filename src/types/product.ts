export type ProductCategory =
  | 'tentes'
  | 'couchage'
  | 'sacs-a-dos'
  | 'cuisine'
  | 'securite';

export interface TechSpecs {
  weightGrams?: number;
  waterproofingMm?: number;
  comfortTempC?: number;
  seasons?: 1 | 2 | 3 | 4;
  capacityLiters?: number;
  material?: string;
}

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
  stock: number;
  ratingValue: number;
  ratingCount: number;
  stripePriceId?: string;
}

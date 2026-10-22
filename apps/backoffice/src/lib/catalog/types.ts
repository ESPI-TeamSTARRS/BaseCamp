// Forme des produits echangés avec /bff/products (miroir de l'API d'administration de shop).

export interface Specs {
  weight_grams?: number;
  waterproofing_mm?: number;
  comfort_temp_c?: number;
  seasons?: number;
  capacity_liters?: number;
  material?: string;
}

export interface Product {
  id: string;
  slug: string;
  name: string;
  category: string;
  price_cents: number;
  compare_at_price_cents: number | null;
  short_description: string;
  description: string;
  specs: Specs;
  stock: number;
  availability: string;
  image_keys: string[];
  image_urls: string[];
  version: number;
  archived_at: string | null;
}

export interface ProductPage {
  items: Product[];
  total: number;
  limit: number;
  offset: number;
}

export const CATEGORIES = [
  { value: 'tentes', label: 'Tentes' },
  { value: 'couchage', label: 'Couchage' },
  { value: 'sacs-a-dos', label: 'Sacs à dos' },
  { value: 'cuisine', label: 'Cuisine' },
  { value: 'securite', label: 'Sécurité' },
] as const;

export function categoryLabel(value: string): string {
  return CATEGORIES.find((category) => category.value === value)?.label ?? value;
}

export const AVAILABILITY_LABELS: Record<string, string> = {
  in_stock: 'En stock',
  low_stock: 'Stock faible',
  out_of_stock: 'Rupture',
};

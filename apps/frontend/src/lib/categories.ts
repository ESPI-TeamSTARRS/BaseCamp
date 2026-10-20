import type { ProductCategory } from '../types/product';

export const categoryLabels: Record<ProductCategory, string> = {
  tentes: 'Tentes & Abris',
  couchage: 'Couchage',
  'sacs-a-dos': 'Sacs à Dos',
  cuisine: 'Camp & Cuisine',
  securite: 'Sécurité & Orientation',
};

export const categorySlugs = Object.keys(categoryLabels) as ProductCategory[];

export function isProductCategory(value: string): value is ProductCategory {
  return Object.prototype.hasOwnProperty.call(categoryLabels, value);
}

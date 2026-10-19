import type { Product } from '../types/product';

const MIN_LEN = 140;
const MAX_LEN = 160;

/**
 * Compose une méta-description entre 140 et 160 caractères (recommandation SEO) en combinant
 * la description courte du produit avec ses caractéristiques techniques et un argument de réassurance.
 */
export function buildProductMetaDescription(product: Product): string {
  const specParts: string[] = [];
  if (product.specs.weightGrams !== undefined) specParts.push(`${product.specs.weightGrams}g`);
  if (product.specs.comfortTempC !== undefined) specParts.push(`${product.specs.comfortTempC}°C confort`);
  if (product.specs.waterproofingMm !== undefined)
    specParts.push(`${product.specs.waterproofingMm}mm Schmerber`);

  const specsSuffix = specParts.length ? ` (${specParts.join(', ')}).` : '.';
  let description = `${product.shortDescription}${specsSuffix}`;

  const reassurance = ' Livraison 24/48h, retours gratuits 30 jours.';
  if (description.length + reassurance.length <= MAX_LEN) {
    description += reassurance;
  }

  if (description.length < MIN_LEN) {
    const padding = ' Équipement testé en conditions réelles de bivouac par Basecamp Outdoor.';
    description = `${description}${padding}`.slice(0, MAX_LEN);
  }

  if (description.length > MAX_LEN) {
    description = `${description.slice(0, MAX_LEN - 1).trimEnd()}…`;
  }

  return description;
}

export function truncateDescription(text: string, maxLen = MAX_LEN): string {
  if (text.length <= maxLen) return text;
  return `${text.slice(0, maxLen - 1).trimEnd()}…`;
}

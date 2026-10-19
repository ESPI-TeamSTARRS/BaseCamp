import { describe, expect, it } from 'vitest';
import type { Product } from '../../types/product';
import { buildProductMetaDescription, truncateDescription } from '../seo';

const baseProduct: Product = {
  id: 'p1',
  slug: 'tente',
  name: 'Tente',
  category: 'tentes',
  priceEur: 100,
  shortDescription: 'Tente ultralegere autoportante pour bivouac en montagne',
  description: 'Description longue',
  images: [],
  specs: { weightGrams: 850, comfortTempC: -5, waterproofingMm: 3000 },
  stock: 5,
  ratingValue: 4.5,
  ratingCount: 10,
};

describe('buildProductMetaDescription', () => {
  it('inclut les caracteristiques techniques', () => {
    const description = buildProductMetaDescription(baseProduct);
    expect(description).toContain('850g');
    expect(description).toContain('-5°C confort');
  });

  it('ne depasse jamais 160 caracteres', () => {
    const long = { ...baseProduct, shortDescription: 'x'.repeat(300) };
    expect(buildProductMetaDescription(long).length).toBeLessThanOrEqual(160);
  });

  it('complete une description trop courte', () => {
    const short = { ...baseProduct, shortDescription: 'Court', specs: {} };
    expect(buildProductMetaDescription(short).length).toBeGreaterThan(60);
  });
});

describe('truncateDescription', () => {
  it('laisse intact un texte court', () => {
    expect(truncateDescription('abc', 10)).toBe('abc');
  });

  it('tronque avec une ellipse', () => {
    expect(truncateDescription('a'.repeat(20), 10)).toHaveLength(10);
  });
});

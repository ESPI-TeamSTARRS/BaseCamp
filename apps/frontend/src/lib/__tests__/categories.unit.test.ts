import { describe, expect, it } from 'vitest';
import { categoryLabels, categorySlugs, isProductCategory } from '../categories';

describe('categories', () => {
  it('expose les cinq categories du catalogue', () => {
    expect(categorySlugs).toEqual(['tentes', 'couchage', 'sacs-a-dos', 'cuisine', 'securite']);
    expect(categoryLabels['sacs-a-dos']).toBe('Sacs à Dos');
  });

  it('reconnait uniquement les categories connues', () => {
    expect(isProductCategory('tentes')).toBe(true);
    expect(isProductCategory('inconnue')).toBe(false);
    expect(isProductCategory('constructor')).toBe(false);
  });
});

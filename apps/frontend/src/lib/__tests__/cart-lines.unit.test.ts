import { describe, expect, it } from 'vitest';
import {
  addLine,
  MAX_QUANTITY,
  removeLine,
  sanitizeStoredLines,
  setLineQuantity,
  type CartProduct,
} from '../cart-lines';

const tente: CartProduct = {
  id: 'tente',
  slug: 'tente',
  name: 'Tente',
  priceEur: 100,
  images: ['/media/tente-1.svg'],
  availability: 'in_stock',
};
const soldOut: CartProduct = { ...tente, id: 'epuise', slug: 'epuise', availability: 'out_of_stock' };

describe('addLine', () => {
  it('ajoute un produit disponible', () => {
    expect(addLine([], tente)).toEqual([{ product: tente, quantity: 1 }]);
  });

  it('cumule les quantites sans depasser le maximum', () => {
    const lines = addLine([{ product: tente, quantity: MAX_QUANTITY - 1 }], tente, 5);

    expect(lines[0].quantity).toBe(MAX_QUANTITY);
  });

  it('refuse un produit en rupture de stock', () => {
    expect(addLine([], soldOut)).toEqual([]);
  });
});

describe('setLineQuantity et removeLine', () => {
  const lines = [{ product: tente, quantity: 2 }];

  it('borne la quantite entre 1 et le maximum', () => {
    expect(setLineQuantity(lines, 'tente', 0)[0].quantity).toBe(1);
    expect(setLineQuantity(lines, 'tente', 99)[0].quantity).toBe(MAX_QUANTITY);
  });

  it('supprime une ligne', () => {
    expect(removeLine(lines, 'tente')).toEqual([]);
  });
});

describe('sanitizeStoredLines', () => {
  it('conserve les lignes valides', () => {
    expect(sanitizeStoredLines([{ product: tente, quantity: 2 }])).toEqual([{ product: tente, quantity: 2 }]);
  });

  it('ignore l ancien format et les donnees invalides', () => {
    expect(sanitizeStoredLines([{ productId: 'tente-ultralight-2p', quantity: 1 }])).toEqual([]);
    expect(sanitizeStoredLines('n importe quoi')).toEqual([]);
    expect(sanitizeStoredLines([{ product: { ...tente, priceEur: 'x' }, quantity: 1 }])).toEqual([]);
  });

  it('borne les quantites stockees et retire les produits en rupture', () => {
    const stored = [
      { product: tente, quantity: 500 },
      { product: soldOut, quantity: 1 },
    ];

    expect(sanitizeStoredLines(stored)).toEqual([{ product: tente, quantity: MAX_QUANTITY }]);
  });
});

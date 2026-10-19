import { describe, expect, it } from 'vitest';
import { CheckoutRequestSchema } from '../validations';

describe('CheckoutRequestSchema', () => {
  it('accepte un panier valide', () => {
    const result = CheckoutRequestSchema.safeParse({ lines: [{ productId: 'p1', quantity: 2 }] });
    expect(result.success).toBe(true);
  });

  it('refuse un panier vide', () => {
    expect(CheckoutRequestSchema.safeParse({ lines: [] }).success).toBe(false);
  });

  it('refuse une quantite hors bornes', () => {
    expect(CheckoutRequestSchema.safeParse({ lines: [{ productId: 'p1', quantity: 11 }] }).success).toBe(
      false
    );
  });

  it('refuse les champs inconnus (strict)', () => {
    const result = CheckoutRequestSchema.safeParse({ lines: [{ productId: 'p1', quantity: 1, price: 1 }] });
    expect(result.success).toBe(false);
  });
});

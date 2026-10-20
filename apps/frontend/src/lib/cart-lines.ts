import type { Availability, Product } from '../types/product';

export const MAX_QUANTITY = 10;

/** Instantané minimal d'un produit conservé dans le panier (l'affichage ne dépend plus d'un catalogue local). */
export type CartProduct = Pick<Product, 'id' | 'slug' | 'name' | 'priceEur' | 'images' | 'availability'>;

export interface CartLine {
  product: CartProduct;
  quantity: number;
}

export function toCartProduct(product: Product): CartProduct {
  const { id, slug, name, priceEur, images, availability } = product;
  return { id, slug, name, priceEur, images: images.slice(0, 1), availability };
}

function clampQuantity(quantity: number): number {
  return Math.max(1, Math.min(Math.trunc(quantity), MAX_QUANTITY));
}

export function addLine(lines: CartLine[], product: CartProduct, quantity = 1): CartLine[] {
  if (product.availability === 'out_of_stock') return lines;
  const existing = lines.find((line) => line.product.id === product.id);
  if (!existing) return [...lines, { product, quantity: clampQuantity(quantity) }];
  return lines.map((line) =>
    line.product.id === product.id ? { ...line, quantity: clampQuantity(line.quantity + quantity) } : line
  );
}

export function setLineQuantity(lines: CartLine[], productId: string, quantity: number): CartLine[] {
  return lines.map((line) =>
    line.product.id === productId ? { ...line, quantity: clampQuantity(quantity) } : line
  );
}

export function removeLine(lines: CartLine[], productId: string): CartLine[] {
  return lines.filter((line) => line.product.id !== productId);
}

const AVAILABILITIES: Availability[] = ['in_stock', 'low_stock', 'out_of_stock'];

function isCartProduct(value: unknown): value is CartProduct {
  if (typeof value !== 'object' || value === null) return false;
  const p = value as Record<string, unknown>;
  return (
    typeof p.id === 'string' &&
    typeof p.slug === 'string' &&
    typeof p.name === 'string' &&
    typeof p.priceEur === 'number' &&
    Array.isArray(p.images) &&
    p.images.every((image) => typeof image === 'string') &&
    AVAILABILITIES.includes(p.availability as Availability)
  );
}

/** Relit le panier du navigateur : ignore l'ancien format et tout ce qui n'est pas valide. */
export function sanitizeStoredLines(raw: unknown): CartLine[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter(
      (line): line is CartLine =>
        typeof line === 'object' && line !== null && isCartProduct((line as CartLine).product)
    )
    .filter((line) => typeof line.quantity === 'number' && line.product.availability !== 'out_of_stock')
    .map((line) => ({ product: line.product, quantity: clampQuantity(line.quantity) }));
}

import { z } from 'zod';

export const CartLineSchema = z
  .object({
    productId: z.string().min(1).max(100),
    quantity: z.number().int().min(1).max(10),
  })
  .strict();

export const CheckoutRequestSchema = z
  .object({
    lines: z.array(CartLineSchema).min(1, 'Le panier est vide').max(50),
  })
  .strict();

export type CheckoutRequest = z.infer<typeof CheckoutRequestSchema>;

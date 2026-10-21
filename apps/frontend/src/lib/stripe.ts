import Stripe from 'stripe';

export const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || 'placeholder_build_only', {
  apiVersion: '2026-09-30.endive',
  typescript: true,
});

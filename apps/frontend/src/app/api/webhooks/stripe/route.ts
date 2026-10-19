import { NextResponse } from 'next/server';
import type Stripe from 'stripe';
import { stripe } from '../../../../lib/stripe';
import { resend } from '../../../../lib/resend';

// Idempotence : évite de traiter deux fois le même événement (retries Stripe).
const processedEventIds = new Set<string>();

export async function POST(req: Request) {
  const body = await req.text(); // corps brut obligatoire pour la vérification de signature
  const signature = req.headers.get('stripe-signature');

  if (!signature) {
    return NextResponse.json({ error: 'Signature manquante' }, { status: 400 });
  }

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(body, signature, process.env.STRIPE_WEBHOOK_SECRET!);
  } catch (err) {
    console.error('[Webhook Security Error]', err instanceof Error ? err.message : 'signature invalide');
    return NextResponse.json({ error: 'Signature invalide' }, { status: 400 });
  }

  if (processedEventIds.has(event.id)) {
    return NextResponse.json({ received: true, duplicate: true });
  }
  processedEventIds.add(event.id);

  try {
    switch (event.type) {
      case 'checkout.session.completed': {
        const session = event.data.object as Stripe.Checkout.Session;
        if (session.customer_details?.email) {
          await resend.emails.send({
            from: process.env.RESEND_FROM_EMAIL ?? 'commandes@basecamp-outdoor.fr',
            to: session.customer_details.email,
            subject: 'Votre commande Basecamp Outdoor est confirmée',
            html: `<p>Merci pour votre commande ! Montant réglé : ${((session.amount_total ?? 0) / 100).toFixed(2)} €.</p><p>Vous recevrez un email de suivi d'expédition dès l'envoi de votre colis (24/48h).</p>`,
          });
        }
        break;
      }
      default:
        break;
    }
  } catch (error) {
    // L'événement Stripe est déjà validé et acquitté : une panne d'envoi d'email ne doit jamais
    // déclencher de retries infinis côté Stripe (webhook toujours acquitté en 200 ci-dessous).
    console.error('[Webhook Side-Effect Error]', error instanceof Error ? error.message : 'unknown');
  }

  return NextResponse.json({ received: true });
}

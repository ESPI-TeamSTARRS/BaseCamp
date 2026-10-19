import { NextResponse } from 'next/server';
import { stripe } from '@/lib/stripe';
import { CheckoutRequestSchema } from '@/lib/validations';
import { products } from '@/lib/products';
import { rateLimit, getClientIp } from '@/lib/rate-limit';

export async function POST(req: Request) {
  try {
    const ip = getClientIp(req);
    const { allowed, retryAfterSeconds } = rateLimit(`checkout:${ip}`, 10);
    if (!allowed) {
      return NextResponse.json(
        { error: 'Trop de tentatives. Merci de réessayer plus tard.' },
        { status: 429, headers: { 'Retry-After': String(retryAfterSeconds) } }
      );
    }

    // Exige explicitement application/json : bloque le contournement CSRF classique qui consiste à
    // envoyer un corps JSON sous Content-Type: text/plain pour éviter le preflight CORS du navigateur.
    const contentType = req.headers.get('content-type') ?? '';
    if (!contentType.toLowerCase().startsWith('application/json')) {
      return NextResponse.json({ error: 'Content-Type invalide, application/json requis.' }, { status: 415 });
    }

    const rawBody = await req.json().catch(() => null);
    const result = CheckoutRequestSchema.safeParse(rawBody);

    if (!result.success) {
      return NextResponse.json(
        { error: 'Panier invalide', details: result.error.flatten().fieldErrors },
        { status: 400 }
      );
    }

    const { lines } = result.data;

    // Chaque productId doit exister dans le catalogue serveur avant toute construction de lineItems.
    // Le message d'erreur ne doit jamais refléter l'entrée brute du client (OWASP A03: Injection).
    const hasUnknownLine = lines.some((line) => !products.some((p) => p.id === line.productId));
    if (hasUnknownLine) {
      return NextResponse.json({ error: 'Un ou plusieurs produits du panier sont introuvables.' }, { status: 400 });
    }

    // Les prix proviennent exclusivement de notre catalogue serveur (jamais du client) pour empêcher toute falsification du montant.
    const lineItems = lines.map((line) => {
      const product = products.find((p) => p.id === line.productId)!;
      return {
        price_data: {
          currency: 'eur',
          product_data: {
            name: product.name,
            images: product.images.length ? [product.images[0]] : undefined,
          },
          unit_amount: Math.round(product.priceEur * 100),
        },
        quantity: line.quantity,
      };
    });

    const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000';
    const session = await stripe.checkout.sessions.create({
      mode: 'payment',
      line_items: lineItems,
      success_url: `${siteUrl}/success?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${siteUrl}/panier`,
      shipping_address_collection: { allowed_countries: ['FR', 'BE', 'CH', 'LU', 'DE', 'ES', 'IT'] },
      allow_promotion_codes: true,
    });

    return NextResponse.json({ url: session.url });
  } catch (error) {
    // Message assaini : jamais de stack trace ni de détail interne renvoyé au client.
    console.error('[Checkout Error]', error instanceof Error ? error.message : 'unknown');
    return NextResponse.json({ error: 'Impossible de créer la session de paiement.' }, { status: 500 });
  }
}

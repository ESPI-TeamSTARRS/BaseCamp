---
name: sec-code-owasp
description: OWASP Top 10 defensive code review & SAST auditor: audits input validation with Zod, Stripe webhook signature verification, secret leakage prevention, dependency CVE scanning, and error handling sanitization.
category: security
---

# OWASP Code Auditor & Vulnerability Remediation (sec-code-owasp)

Guide d'audit défensif du code source et des routes API Next.js / TypeScript pour éliminer les vulnérabilités de l'OWASP Top 10.

## 1. Validation Stricte des Entrées (Injection & Paramètres Malformés)

Ne jamais faire confiance aux requêtes entrantes (`req.json()`). Toute entrée doit être validée par un schéma strict (ex: Zod) avant tout traitement :

```typescript
import { z } from 'zod';
import { NextResponse } from 'next/server';

const CheckoutSchema = z.object({
  tier: z.enum(['solo', 'duo'], {
    errorMap: () => ({ message: "Offre invalide (solo ou duo uniquement)" })
  }),
  referralCode: z.string().max(20).optional(),
}).strict(); // .strict() rejette tout champ imprévu injecté

export async function POST(req: Request) {
  try {
    const rawBody = await req.json().catch(() => null);
    const result = CheckoutSchema.safeParse(rawBody);
    
    if (!result.success) {
      return NextResponse.json(
        { error: 'Données de requête invalides', details: result.error.flatten().fieldErrors },
        { status: 400 }
      );
    }
    const { tier } = result.data;
    // Poursuivre le traitement...
  } catch (error) {
    return NextResponse.json({ error: 'Erreur interne' }, { status: 500 });
  }
}
```

## 2. Sécurité des Webhooks Stripe (Contrefaçon de Requête)

Le webhook Stripe est critique pour la validation des paiements. Les règles absolues :
1. **Toujours valider la signature cryptographique** via `stripe.webhooks.constructEvent(body, signature, secret)`.
2. **Utiliser le corps brut (Raw Buffer/Text)**, jamais un JSON parsé (`await req.text()`).
3. **Idempotence** : Enregistrer ou vérifier l'ID d'événement (`event.id`) pour éviter les doubles déclenchements.
4. **Constante temporelle** : Rejeter les timestamps expirés (géré nativement par le SDK Stripe).

```typescript
export async function POST(req: Request) {
  const body = await req.text();
  const signature = req.headers.get('stripe-signature');

  if (!signature) {
    return NextResponse.json({ error: 'Signature manquante' }, { status: 400 });
  }

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(
      body,
      signature,
      process.env.STRIPE_WEBHOOK_SECRET!
    );
  } catch (err: any) {
    console.error(`[Webhook Security Error]: ${err.message}`);
    return NextResponse.json({ error: 'Signature invalide' }, { status: 400 });
  }

  // Traitement sécurisé selon event.type...
  return NextResponse.json({ received: true }, { status: 200 });
}
```

## 3. Gestion des Secrets & Variables d'Environnement

- **Préfixe `NEXT_PUBLIC_`** : Doit être réservé exclusivement aux variables consommées côté navigateur (ex: domaine public, Stripe Publishable Key).
- **Secrets Serveur** : `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, tokens Telegram/Discord ne doivent **JAMAIS** porter le préfixe `NEXT_PUBLIC_`.
- **Fichier `.env`** : Vérifier impérativement que `.env`, `.env.local`, `.

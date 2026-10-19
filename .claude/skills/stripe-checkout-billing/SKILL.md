---
name: stripe-checkout-billing
description: Intégration de paiements Stripe : Checkout Sessions, vérification cryptographique des webhooks, idempotence, gestion d'abonnements et portail client.
category: software-development
---

# Stripe Checkout & Billing Integration Specialist

Guide d'implémentation sécurisée pour les paiements en ligne et abonnements SaaS avec Stripe.

## 1. Création d'une Session Checkout

```python
import stripe

stripe.api_key = "sk_live_..."

def create_subscription_checkout(customer_email: str, price_id: str, client_ref_id: str):
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="subscription",
        line_items=[{
            "price": price_id,
            "quantity": 1,
        }],
        customer_email=customer_email,
        client_reference_id=client_ref_id,
        success_url="https://domaine.fr/billing/success?session_id={CHECKOUT_SESSION_ID}",
        cancel_url="https://domaine.fr/billing/cancel",
        allow_promotion_codes=True,
        billing_address_collection="auto",
    )
    return session.url
```

## 2. Vérification Cryptographique des Webhooks

**Règle absolue :** Ne jamais se fier aux données reçues sans vérifier la signature du webhook avec le payload brut (raw body).

```python
from fastapi import FastAPI, Request, HTTPException, status
import stripe

WEBHOOK_SECRET = "whsec_..."

@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload invalide")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Signature non vérifiée")

    event_type = event["type"]
    data_object = event["data"]["object"]

    if event_type == "checkout.session.completed":
        handle_checkout_completed(data_object)
    elif event_type == "invoice.payment_succeeded":
        handle_payment_success(data_object)
    elif event_type == "customer.subscription.deleted":
        handle_subscription_cancelled(data_object)

    return {"status": "success"}
```

## 3. Portail Client Stripe

Permettre aux clients de modifier leur carte bancaire, télécharger leurs factures et gérer leur abonnement en toute autonomie :
```python
def create_customer_portal(customer_id: str, return_url: str) -> str:
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return session.url
```

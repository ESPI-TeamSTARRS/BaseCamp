import { z } from 'zod';

const ORDERS_URL = '/api/shop/orders';
const REQUEST_TIMEOUT_MS = 10000;
const ORDER_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const NOT_PAYABLE_MESSAGE = 'Cette commande ne peut plus être payée.';

const ApiIntentSchema = z.object({
  payment_intent_id: z.string(),
  amount_cents: z.number().int(),
  order_number: z.string(),
  payment_methods: z.array(z.string()),
});

const ApiConfirmationSchema = z.object({
  order_number: z.string(),
  order_status: z.string(),
  payment_status: z.string(),
});

export type TestPaymentMethod = 'pm_test_success' | 'pm_test_declined';

export interface PaymentRequest {
  intentId: string;
  orderNumber: string;
  amountEur: number;
  methods: string[];
}

export interface PaymentResult {
  orderNumber: string;
  orderStatus: string;
  paymentStatus: string;
}

type Failure =
  | { ok: false; reason: 'not_payable'; message: string }
  | { ok: false; reason: 'not_found' }
  | { ok: false; reason: 'unavailable' };

export type RequestPaymentResult = { ok: true; payment: PaymentRequest } | Failure;
export type ConfirmPaymentResult = { ok: true; result: PaymentResult } | Failure;
type FetchLike = typeof fetch;

export function isOrderId(value: string): boolean {
  return ORDER_ID.test(value);
}

async function failureFor(response: Response): Promise<Failure> {
  if (response.status === 404) return { ok: false, reason: 'not_found' };
  if (response.status === 409) {
    const body: unknown = await response.json().catch(() => null);
    const detail = (body as { detail?: unknown } | null)?.detail;
    return {
      ok: false,
      reason: 'not_payable',
      message: typeof detail === 'string' ? detail : NOT_PAYABLE_MESSAGE,
    };
  }
  return { ok: false, reason: 'unavailable' };
}

async function post(path: string, body: unknown, fetchImpl: FetchLike): Promise<Response> {
  return fetchImpl(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: 'no-store',
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });
}

/** Demande l'intention de paiement d'une commande : le montant vient toujours du serveur. */
export async function requestPayment(
  orderId: string,
  fetchImpl: FetchLike = fetch
): Promise<RequestPaymentResult> {
  if (!isOrderId(orderId)) return { ok: false, reason: 'not_found' };
  try {
    const response = await post(`${ORDERS_URL}/${orderId}/pay`, undefined, fetchImpl);
    if (!response.ok) return await failureFor(response);
    const raw = ApiIntentSchema.parse(await response.json());
    return {
      ok: true,
      payment: {
        intentId: raw.payment_intent_id,
        orderNumber: raw.order_number,
        amountEur: raw.amount_cents / 100,
        methods: raw.payment_methods,
      },
    };
  } catch {
    return { ok: false, reason: 'unavailable' };
  }
}

/** Confirme avec une méthode de test : aucun numéro de carte n'existe dans ce contrat. */
export async function confirmPayment(
  orderId: string,
  method: TestPaymentMethod,
  fetchImpl: FetchLike = fetch
): Promise<ConfirmPaymentResult> {
  if (!isOrderId(orderId)) return { ok: false, reason: 'not_found' };
  try {
    const response = await post(
      `${ORDERS_URL}/${orderId}/pay/confirm`,
      { payment_method: method },
      fetchImpl
    );
    if (!response.ok) return await failureFor(response);
    const raw = ApiConfirmationSchema.parse(await response.json());
    return {
      ok: true,
      result: {
        orderNumber: raw.order_number,
        orderStatus: raw.order_status,
        paymentStatus: raw.payment_status,
      },
    };
  } catch {
    return { ok: false, reason: 'unavailable' };
  }
}

export const PAYMENT_UNAVAILABLE_MESSAGE =
  'Le paiement est momentanément indisponible. Réessayez dans un instant.';
const ORDER_NOT_FOUND_MESSAGE = 'Commande introuvable.';

export type PaymentLoadView =
  | { step: 'ready'; payment: PaymentRequest; declined: false }
  | { step: 'error'; message: string; retry: boolean };

/**
 * Vue à afficher pour une première demande de paiement. Ne rejette jamais : une exception
 * inattendue devient « indisponible » avec possibilité de réessayer.
 */
export async function loadPaymentView(
  orderId: string,
  request: (orderId: string) => Promise<RequestPaymentResult> = requestPayment
): Promise<PaymentLoadView> {
  let result: RequestPaymentResult;
  try {
    result = await request(orderId);
  } catch {
    return { step: 'error', message: PAYMENT_UNAVAILABLE_MESSAGE, retry: true };
  }
  if (result.ok) return { step: 'ready', payment: result.payment, declined: false };
  if (result.reason === 'not_payable') return { step: 'error', message: result.message, retry: false };
  if (result.reason === 'not_found') return { step: 'error', message: ORDER_NOT_FOUND_MESSAGE, retry: false };
  return { step: 'error', message: PAYMENT_UNAVAILABLE_MESSAGE, retry: true };
}

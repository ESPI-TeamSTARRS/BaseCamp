import { describe, expect, it, vi } from 'vitest';
import {
  confirmPayment,
  isOrderId,
  loadPaymentView,
  requestPayment,
  type RequestPaymentResult,
} from '../order-payment';

const ORDER_ID = '0b6b1f2e-6c52-4d3b-8a52-1d6f7a9b2c10';

const apiIntent = {
  payment_intent_id: 'pi-1',
  status: 'requires_confirmation',
  amount_cents: 4490,
  currency: 'EUR',
  order_number: 'BC-ABCDEFGHJK',
  payment_methods: ['pm_test_success', 'pm_test_declined'],
};

function reply(status: number, body: unknown): typeof fetch {
  return vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;
}

describe('isOrderId', () => {
  it('accepte un UUID et refuse tout le reste', () => {
    expect(isOrderId(ORDER_ID)).toBe(true);
    expect(isOrderId('BC-ABCDEFGHJK')).toBe(false);
    expect(isOrderId('../admin')).toBe(false);
    expect(isOrderId('')).toBe(false);
  });
});

describe('requestPayment', () => {
  it("demande l'intention de la commande et renvoie le montant, le numéro et les méthodes de test", async () => {
    const fetchImpl = reply(201, apiIntent);

    const result = await requestPayment(ORDER_ID, fetchImpl);

    expect(result).toEqual({
      ok: true,
      payment: {
        intentId: 'pi-1',
        orderNumber: 'BC-ABCDEFGHJK',
        amountEur: 44.9,
        methods: ['pm_test_success', 'pm_test_declined'],
      },
    });
    const [url, init] = (fetchImpl as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`/api/shop/orders/${ORDER_ID}/pay`);
    expect(init.method).toBe('POST');
  });

  it('accepte aussi la réponse 200 d’un rejeu', async () => {
    expect(await requestPayment(ORDER_ID, reply(200, apiIntent))).toMatchObject({ ok: true });
  });

  it('traduit un 409 en commande non payable avec le message fixe du serveur', async () => {
    const result = await requestPayment(ORDER_ID, reply(409, { detail: 'Commande deja payee.' }));
    expect(result).toEqual({ ok: false, reason: 'not_payable', message: 'Commande deja payee.' });
  });

  it('traduit un 404 en commande introuvable', async () => {
    expect(await requestPayment(ORDER_ID, reply(404, { detail: 'Commande introuvable.' }))).toEqual({
      ok: false,
      reason: 'not_found',
    });
  });

  it('signale le service indisponible sur 503, erreur réseau ou réponse inattendue', async () => {
    const failing = vi.fn().mockRejectedValue(new Error('réseau')) as unknown as typeof fetch;
    expect(await requestPayment(ORDER_ID, reply(503, {}))).toEqual({ ok: false, reason: 'unavailable' });
    expect(await requestPayment(ORDER_ID, failing)).toEqual({ ok: false, reason: 'unavailable' });
    expect(await requestPayment(ORDER_ID, reply(201, { nope: true }))).toEqual({
      ok: false,
      reason: 'unavailable',
    });
  });

  it("refuse d'appeler le serveur avec un identifiant qui n'est pas un UUID", async () => {
    const fetchImpl = reply(201, apiIntent);
    expect(await requestPayment('../admin', fetchImpl)).toEqual({ ok: false, reason: 'not_found' });
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});

describe('confirmPayment', () => {
  const confirmed = { order_number: 'BC-ABCDEFGHJK', order_status: 'paid', payment_status: 'succeeded' };

  it('envoie une méthode de test (jamais de donnée de carte) et renvoie le résultat', async () => {
    const fetchImpl = reply(200, confirmed);

    const result = await confirmPayment(ORDER_ID, 'pm_test_success', fetchImpl);

    expect(result).toEqual({
      ok: true,
      result: { orderNumber: 'BC-ABCDEFGHJK', orderStatus: 'paid', paymentStatus: 'succeeded' },
    });
    const [url, init] = (fetchImpl as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`/api/shop/orders/${ORDER_ID}/pay/confirm`);
    expect(JSON.parse(init.body)).toEqual({ payment_method: 'pm_test_success' });
    expect(init.headers['Content-Type']).toBe('application/json');
  });

  it('un refus est un résultat métier, pas une erreur', async () => {
    const result = await confirmPayment(
      ORDER_ID,
      'pm_test_declined',
      reply(200, { ...confirmed, order_status: 'pending_payment', payment_status: 'failed' })
    );
    expect(result).toMatchObject({
      ok: true,
      result: { paymentStatus: 'failed', orderStatus: 'pending_payment' },
    });
  });

  it('traduit un 409 en commande non payable (déjà payée, expirée ou sans paiement en attente)', async () => {
    const result = await confirmPayment(
      ORDER_ID,
      'pm_test_success',
      reply(409, { detail: 'Commande expiree.' })
    );
    expect(result).toEqual({ ok: false, reason: 'not_payable', message: 'Commande expiree.' });
  });

  it('signale le service indisponible', async () => {
    expect(await confirmPayment(ORDER_ID, 'pm_test_success', reply(503, {}))).toEqual({
      ok: false,
      reason: 'unavailable',
    });
  });

  it('retombe sur un message générique si le 409 n’a pas de détail texte', async () => {
    const result = await confirmPayment(ORDER_ID, 'pm_test_success', reply(409, {}));
    expect(result).toMatchObject({ ok: false, reason: 'not_payable' });
    expect((result as { message: string }).message).toMatch(/\S/);
  });
});

describe('loadPaymentView', () => {
  const payment = {
    intentId: 'pi-1',
    orderNumber: 'BC-ABCDEFGHJK',
    amountEur: 44.9,
    methods: ['pm_test_success'],
  };
  const viewFor = (result: RequestPaymentResult) =>
    loadPaymentView(ORDER_ID, vi.fn().mockResolvedValue(result));

  it("présente l'intention reçue, sans refus", async () => {
    expect(await viewFor({ ok: true, payment })).toEqual({ step: 'ready', payment, declined: false });
  });

  it('explique une commande qui ne peut plus être payée, sans nouvel essai', async () => {
    expect(await viewFor({ ok: false, reason: 'not_payable', message: 'Commande deja payee.' })).toEqual({
      step: 'error',
      message: 'Commande deja payee.',
      retry: false,
    });
  });

  it('signale une commande introuvable, sans nouvel essai', async () => {
    expect(await viewFor({ ok: false, reason: 'not_found' })).toEqual({
      step: 'error',
      message: 'Commande introuvable.',
      retry: false,
    });
  });

  it('propose un nouvel essai quand le paiement est indisponible', async () => {
    const view = await viewFor({ ok: false, reason: 'unavailable' });

    expect(view).toMatchObject({ step: 'error', retry: true });
  });

  it('ne rejette jamais : une exception inattendue devient « indisponible » avec nouvel essai', async () => {
    const request = vi.fn().mockRejectedValue(new Error('boom'));

    const view = await loadPaymentView(ORDER_ID, request);

    expect(view).toMatchObject({ step: 'error', retry: true });
  });
});

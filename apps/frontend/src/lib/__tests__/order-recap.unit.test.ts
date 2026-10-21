import { describe, expect, it, vi } from 'vitest';
import type { LookupResult, TrackedOrder } from '../order-lookup';
import { loadRecap, rememberLastOrder } from '../order-recap';

const NUMBER = 'BC-ABCDEFGHJK';
const EMAIL = 'camille.martin@example.org';

const order: TrackedOrder = {
  number: NUMBER,
  status: 'paid',
  statusLabel: 'Payée',
  lines: [{ name: 'Popote en titane', unitPriceEur: 39, quantity: 1, lineTotalEur: 39 }],
  subtotalEur: 39,
  shippingEur: 5.9,
  totalEur: 44.9,
  createdAt: '2026-10-21T09:00:00Z',
};

class MemoryStorage {
  private readonly items = new Map<string, string>();
  getItem(key: string) {
    return this.items.get(key) ?? null;
  }
  setItem(key: string, value: string) {
    this.items.set(key, value);
  }
}

const asStorage = (storage: MemoryStorage) => storage as unknown as Storage;
const lookupReturning = (result: LookupResult) => vi.fn().mockResolvedValue(result);

describe('loadRecap', () => {
  it('affiche le récapitulatif réel renvoyé par le serveur pour la commande mémorisée', async () => {
    const storage = new MemoryStorage();
    rememberLastOrder(asStorage(storage), NUMBER, EMAIL);
    const lookup = lookupReturning({ ok: true, order });

    const result = await loadRecap(NUMBER, asStorage(storage), lookup);

    expect(result).toEqual({ kind: 'recap', order });
    expect(lookup).toHaveBeenCalledWith(NUMBER, EMAIL);
  });

  it("n'utilise jamais l'email d'une autre commande", async () => {
    const storage = new MemoryStorage();
    rememberLastOrder(asStorage(storage), 'BC-ZZZZZZZZZZ', EMAIL);
    const lookup = lookupReturning({ ok: true, order });

    const result = await loadRecap(NUMBER, asStorage(storage), lookup);

    expect(result).toEqual({ kind: 'no_email' });
    expect(lookup).not.toHaveBeenCalled();
  });

  it("propose le suivi manuel quand rien n'est mémorisé ou que le stockage est indisponible", async () => {
    const lookup = lookupReturning({ ok: true, order });

    expect(await loadRecap(NUMBER, asStorage(new MemoryStorage()), lookup)).toEqual({
      kind: 'no_email',
    });
    expect(await loadRecap(NUMBER, undefined, lookup)).toEqual({ kind: 'no_email' });
    expect(lookup).not.toHaveBeenCalled();
  });

  it('traduit les échecs de la recherche sans jamais rejeter', async () => {
    const storage = new MemoryStorage();
    rememberLastOrder(asStorage(storage), NUMBER, EMAIL);

    expect(
      await loadRecap(NUMBER, asStorage(storage), lookupReturning({ ok: false, reason: 'not_found' }))
    ).toEqual({ kind: 'no_email' });
    expect(
      await loadRecap(NUMBER, asStorage(storage), lookupReturning({ ok: false, reason: 'unavailable' }))
    ).toEqual({ kind: 'unavailable' });
    expect(await loadRecap(NUMBER, asStorage(storage), vi.fn().mockRejectedValue(new Error('boom')))).toEqual(
      { kind: 'unavailable' }
    );
  });
});

describe('rememberLastOrder', () => {
  it("ne lève jamais quand le stockage de l'onglet est refusé", () => {
    const refusing = {
      getItem: () => {
        throw new Error('denied');
      },
      setItem: () => {
        throw new Error('denied');
      },
    } as unknown as Storage;

    expect(() => rememberLastOrder(refusing, NUMBER, EMAIL)).not.toThrow();
    expect(() => rememberLastOrder(undefined, NUMBER, EMAIL)).not.toThrow();
  });

  it("garde le dernier numéro et l'email dans un seul enregistrement", () => {
    const storage = new MemoryStorage();

    rememberLastOrder(asStorage(storage), NUMBER, EMAIL);

    expect(JSON.parse(storage.getItem('basecamp:last-order') ?? '{}')).toEqual({
      number: NUMBER,
      email: EMAIL,
    });
  });
});

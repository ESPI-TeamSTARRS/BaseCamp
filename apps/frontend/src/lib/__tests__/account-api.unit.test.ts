import { describe, expect, it, vi } from 'vitest';
import { registerAccount, verifyEmailToken } from '../account-api';

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

describe('registerAccount', () => {
  it('poste email et mot de passe sur la passerelle et accepte un 202', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ message: 'ok' }, 202));

    const result = await registerAccount('camille@example.com', 'sentier-du-mont-blanc', fetchImpl);

    expect(result).toEqual({ ok: true });
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe('/api/auth/register');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({
      email: 'camille@example.com',
      password: 'sentier-du-mont-blanc',
    });
    expect(init.credentials).toBe('same-origin');
  });

  it('remonte les champs et messages d une validation 422', async () => {
    const body = {
      detail: 'Requête invalide.',
      fields: ['password'],
      messages: ['Ce mot de passe est trop courant.'],
    };
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(body, 422));

    const result = await registerAccount('camille@example.com', 'Password1234', fetchImpl);

    expect(result).toEqual({
      ok: false,
      kind: 'invalid',
      fields: ['password'],
      messages: ['Ce mot de passe est trop courant.'],
    });
  });

  it('tolere un 422 sans messages (validation de schema)', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(jsonResponse({ detail: 'Requête invalide.', fields: ['email'] }, 422));

    const result = await registerAccount('x', 'y', fetchImpl);

    expect(result).toEqual({ ok: false, kind: 'invalid', fields: ['email'], messages: [] });
  });

  it('distingue la limitation de debit (429)', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('Too Many Requests', { status: 429 }));

    expect(await registerAccount('a@b.co', 'x'.repeat(12), fetchImpl)).toEqual({
      ok: false,
      kind: 'rate_limited',
    });
  });

  it.each([500, 502, 404])('traite un statut %s comme indisponible, sans detail', async (status) => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('<html>stack trace</html>', { status }));

    expect(await registerAccount('a@b.co', 'x'.repeat(12), fetchImpl)).toEqual({
      ok: false,
      kind: 'unavailable',
    });
  });

  it('traite une erreur reseau et un corps illisible comme indisponible', async () => {
    const network = vi.fn().mockRejectedValue(new TypeError('failed to fetch'));
    const garbage = vi.fn().mockResolvedValue(new Response('pas du json', { status: 422 }));

    expect(await registerAccount('a@b.co', 'x'.repeat(12), network)).toEqual({
      ok: false,
      kind: 'unavailable',
    });
    expect(await registerAccount('a@b.co', 'x'.repeat(12), garbage)).toEqual({
      ok: false,
      kind: 'unavailable',
    });
  });
});

describe('verifyEmailToken', () => {
  it('confirme avec un 200', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ message: 'ok' }, 200));

    expect(await verifyEmailToken('jeton', fetchImpl)).toEqual({ ok: true });
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe('/api/auth/verify-email');
    expect(JSON.parse(init.body)).toEqual({ token: 'jeton' });
  });

  it('rend une erreur generique pour un lien invalide (400) ou mal forme (422)', async () => {
    for (const status of [400, 422]) {
      const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ detail: 'x' }, status));
      expect(await verifyEmailToken('jeton', fetchImpl)).toEqual({ ok: false, kind: 'invalid' });
    }
  });

  it('traite les autres echecs comme indisponible', async () => {
    expect(
      await verifyEmailToken('jeton', vi.fn().mockResolvedValue(new Response('', { status: 503 })))
    ).toEqual({
      ok: false,
      kind: 'unavailable',
    });
    expect(await verifyEmailToken('jeton', vi.fn().mockRejectedValue(new Error('boom')))).toEqual({
      ok: false,
      kind: 'unavailable',
    });
  });
});

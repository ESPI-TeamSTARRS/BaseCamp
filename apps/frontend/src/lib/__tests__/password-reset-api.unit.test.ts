import { describe, expect, it, vi } from 'vitest';
import { requestPasswordReset, resetPassword } from '../account-api';

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

describe('requestPasswordReset', () => {
  it('poste l email sur la passerelle et accepte le 202 neutre', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ message: 'ok' }, 202));

    const result = await requestPasswordReset('camille@example.com', fetchImpl);

    expect(result).toEqual({ ok: true });
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe('/api/auth/password/forgot');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ email: 'camille@example.com' });
    expect(init.credentials).toBe('same-origin');
  });

  it('distingue la limitation de debit (429)', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('Too Many Requests', { status: 429 }));

    expect(await requestPasswordReset('a@b.co', fetchImpl)).toEqual({ ok: false, kind: 'rate_limited' });
  });

  it.each([500, 502, 404, 422])('traite un statut %s comme indisponible, sans detail', async (status) => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('<html>stack trace</html>', { status }));

    expect(await requestPasswordReset('a@b.co', fetchImpl)).toEqual({ ok: false, kind: 'unavailable' });
  });

  it('traite une erreur reseau comme indisponible', async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError('failed to fetch'));

    expect(await requestPasswordReset('a@b.co', fetchImpl)).toEqual({ ok: false, kind: 'unavailable' });
  });
});

describe('resetPassword', () => {
  it('poste le jeton et le nouveau mot de passe, accepte un 200', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ message: 'ok' }, 200));

    const result = await resetPassword('jeton', 'sentier-du-mont-blanc', fetchImpl);

    expect(result).toEqual({ ok: true });
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe('/api/auth/password/reset');
    expect(JSON.parse(init.body)).toEqual({ token: 'jeton', password: 'sentier-du-mont-blanc' });
  });

  it('rend invalid_token pour le 400 generique', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ detail: 'x' }, 400));

    expect(await resetPassword('jeton', 'x'.repeat(12), fetchImpl)).toEqual({
      ok: false,
      kind: 'invalid_token',
    });
  });

  it('remonte le message serveur quand le mot de passe est refuse (422 sur password)', async () => {
    const body = {
      detail: 'Requête invalide.',
      fields: ['password'],
      messages: ['Ce mot de passe est trop courant.'],
    };
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(body, 422));

    expect(await resetPassword('jeton', 'Password1234', fetchImpl)).toEqual({
      ok: false,
      kind: 'weak_password',
      message: 'Ce mot de passe est trop courant.',
    });
  });

  it('traite un 422 sur le jeton (forme invalide) comme un lien invalide', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ detail: 'x', fields: ['token'] }, 422));

    expect(await resetPassword('', 'x'.repeat(12), fetchImpl)).toEqual({ ok: false, kind: 'invalid_token' });
  });

  it('retombe sur un message generique si le 422 de mot de passe n en porte pas', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ fields: ['password'] }, 422));

    expect(await resetPassword('jeton', 'x', fetchImpl)).toEqual({
      ok: false,
      kind: 'weak_password',
      message: 'Ce mot de passe est refusé.',
    });
  });

  it('traite un 422 illisible comme indisponible', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('pas du json', { status: 422 }));

    expect(await resetPassword('jeton', 'x', fetchImpl)).toEqual({ ok: false, kind: 'unavailable' });
  });

  it('distingue le debit (429) et traite le reste comme indisponible', async () => {
    expect(
      await resetPassword('j', 'x', vi.fn().mockResolvedValue(new Response('', { status: 429 })))
    ).toEqual({ ok: false, kind: 'rate_limited' });
    expect(
      await resetPassword('j', 'x', vi.fn().mockResolvedValue(new Response('', { status: 503 })))
    ).toEqual({ ok: false, kind: 'unavailable' });
    expect(await resetPassword('j', 'x', vi.fn().mockRejectedValue(new Error('boom')))).toEqual({
      ok: false,
      kind: 'unavailable',
    });
  });
});

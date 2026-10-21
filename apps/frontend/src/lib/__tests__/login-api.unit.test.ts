import { describe, expect, it, vi } from 'vitest';
import { loginAccount } from '../login-api';

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

describe('loginAccount', () => {
  it('poste email et mot de passe sur la passerelle et renvoie le jeton d acces', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(
        jsonResponse({ access_token: 'jeton.d.acces', token_type: 'Bearer', expires_in: 900 }, 200)
      );

    const result = await loginAccount('camille@example.com', 'sentier-du-mont-blanc', fetchImpl);

    expect(result).toEqual({ ok: true, accessToken: 'jeton.d.acces', expiresIn: 900 });
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe('/api/auth/login');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({
      email: 'camille@example.com',
      password: 'sentier-du-mont-blanc',
    });
    // Le cookie de rafraichissement (HttpOnly) est pose par le navigateur sur la meme origine.
    expect(init.credentials).toBe('same-origin');
  });

  it('distingue des identifiants refuses (401) sans rien reveler d autre', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ detail: 'Identifiants invalides.' }, 401));

    expect(await loginAccount('a@b.co', 'x', fetchImpl)).toEqual({ ok: false, kind: 'invalid_credentials' });
  });

  it('signale une limitation de debit (429)', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('', { status: 429 }));

    expect(await loginAccount('a@b.co', 'x', fetchImpl)).toEqual({ ok: false, kind: 'rate_limited' });
  });

  it('traite une validation 422 comme une saisie invalide', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ detail: 'Requete invalide.' }, 422));

    expect(await loginAccount('a@b.co', 'x', fetchImpl)).toEqual({ ok: false, kind: 'invalid' });
  });

  it.each([500, 502, 503])('traite un %i comme indisponible', async (status) => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('', { status }));

    expect(await loginAccount('a@b.co', 'x', fetchImpl)).toEqual({ ok: false, kind: 'unavailable' });
  });

  it('traite un corps de succes inattendu comme indisponible', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ access_token: 42 }, 200));

    expect(await loginAccount('a@b.co', 'x', fetchImpl)).toEqual({ ok: false, kind: 'unavailable' });
  });

  it('ne leve jamais d exception reseau', async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError('fetch failed'));

    expect(await loginAccount('a@b.co', 'x', fetchImpl)).toEqual({ ok: false, kind: 'unavailable' });
  });
});

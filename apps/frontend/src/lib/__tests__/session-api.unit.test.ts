import { describe, expect, it, vi } from 'vitest';
import { refreshAccessToken, revokeRefreshToken } from '../session-api';

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

describe('refreshAccessToken', () => {
  it('echange le cookie contre un jeton d acces, avec l en-tete anti-CSRF', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(jsonResponse({ access_token: 'neuf', token_type: 'Bearer', expires_in: 900 }, 200));

    const result = await refreshAccessToken(fetchImpl);

    expect(result).toEqual({ ok: true, accessToken: 'neuf', expiresIn: 900 });
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe('/api/auth/refresh');
    expect(init.method).toBe('POST');
    expect(init.headers['x-requested-with']).toBeTruthy();
    expect(init.credentials).toBe('same-origin');
    expect(init.body).toBeUndefined();
  });

  it('traite un 401 comme une session terminee', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ detail: 'Session expirée.' }, 401));

    expect(await refreshAccessToken(fetchImpl)).toEqual({ ok: false, kind: 'expired' });
  });

  it.each([403, 429, 500, 503])('traite un %i comme indisponible', async (status) => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('', { status }));

    expect(await refreshAccessToken(fetchImpl)).toEqual({ ok: false, kind: 'unavailable' });
  });

  it('traite un corps inattendu comme indisponible', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ access_token: '' }, 200));

    expect(await refreshAccessToken(fetchImpl)).toEqual({ ok: false, kind: 'unavailable' });
  });

  it('ne lance jamais d exception sur une panne reseau', async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new Error('reseau'));

    expect(await refreshAccessToken(fetchImpl)).toEqual({ ok: false, kind: 'unavailable' });
  });
});

describe('revokeRefreshToken', () => {
  it('appelle la deconnexion avec l en-tete anti-CSRF et le cookie', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));

    await revokeRefreshToken(fetchImpl);

    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe('/api/auth/logout');
    expect(init.method).toBe('POST');
    expect(init.headers['x-requested-with']).toBeTruthy();
    expect(init.credentials).toBe('same-origin');
  });

  it('ignore une panne reseau', async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new Error('reseau'));

    await expect(revokeRefreshToken(fetchImpl)).resolves.toBeUndefined();
  });
});

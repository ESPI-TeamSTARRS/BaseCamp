import { describe, expect, it, vi } from 'vitest';
import { AuthBackofficeClient } from '../auth-backoffice-client';

const BASE = 'http://auth:8000';
const CONTEXT = { correlationId: 'corr-12345678', forwardedFor: '203.0.113.7' };
const json = (status: number, body: unknown = {}) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

describe('identify', () => {
  it('envoie l’adresse à /backoffice/identify avec la corrélation et l’adresse source, et lit le défi', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(json(200, { challenge_id: 'defi-opaque-0123456789', expires_in: 120 }));

    const result = await new AuthBackofficeClient(BASE, fetchImpl).identify('op@example.org', CONTEXT);

    expect(result).toEqual({ kind: 'ok', challengeId: 'defi-opaque-0123456789', expiresIn: 120 });
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(url).toBe('http://auth:8000/backoffice/identify');
    expect(JSON.parse(init.body as string)).toEqual({ email: 'op@example.org' });
    expect(headers.get('x-correlation-id')).toBe('corr-12345678');
    expect(headers.get('x-forwarded-for')).toBe('203.0.113.7');
    expect(init.redirect).toBe('error');
  });

  it('traduit une panne, un statut inattendu ou une réponse illisible en « unavailable »', async () => {
    for (const fetchImpl of [
      vi.fn().mockRejectedValue(new Error('refusé')),
      vi.fn().mockResolvedValue(json(500)),
      vi.fn().mockResolvedValue(json(200, { pas: 'de défi' })),
      vi.fn().mockResolvedValue(new Response('pas du json', { status: 200 })),
    ]) {
      expect(await new AuthBackofficeClient(BASE, fetchImpl).identify('a@b.c', CONTEXT)).toEqual({
        kind: 'unavailable',
      });
    }
  });
});

describe('face', () => {
  it('relaie les images et lit le résultat', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(json(200, { face_ok: true }));

    const result = await new AuthBackofficeClient(BASE, fetchImpl).face(
      'defi-opaque-0123456789',
      ['aGVsbG8='],
      CONTEXT
    );

    expect(result).toEqual({ kind: 'ok' });
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('http://auth:8000/backoffice/face');
    expect(JSON.parse(init.body as string)).toEqual({
      challenge_id: 'defi-opaque-0123456789',
      images: ['aGVsbG8='],
    });
  });

  it('distingue refus (401), image invalide (422) et le reste', async () => {
    const run = (response: Response | Error) =>
      new AuthBackofficeClient(
        BASE,
        response instanceof Error ? vi.fn().mockRejectedValue(response) : vi.fn().mockResolvedValue(response)
      ).face('d', ['x'], CONTEXT);

    expect(await run(json(401))).toEqual({ kind: 'refused' });
    expect(await run(json(422))).toEqual({ kind: 'invalid_images' });
    expect(await run(json(409))).toEqual({ kind: 'unavailable' });
    expect(await run(json(200, {}))).toEqual({ kind: 'unavailable' });
    expect(await run(new Error('x'))).toEqual({ kind: 'unavailable' });
  });
});

describe('password', () => {
  it('rend le jeton d’accès et sa durée (sans cookie de rafraîchissement)', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(json(200, { access_token: 'a.b.c', token_type: 'Bearer', expires_in: 900 }));

    const result = await new AuthBackofficeClient(BASE, fetchImpl).password(
      'defi-opaque-0123456789',
      'mot-de-passe-de-test',
      CONTEXT
    );

    expect(result).toEqual({ kind: 'ok', accessToken: 'a.b.c', expiresIn: 900 });
    expect(JSON.parse((fetchImpl.mock.calls[0] as [string, RequestInit])[1].body as string)).toEqual({
      challenge_id: 'defi-opaque-0123456789',
      password: 'mot-de-passe-de-test',
    });
  });

  it('un 401 est un refus ; panne, 5xx et réponse incomplète sont « unavailable »', async () => {
    const run = (response: Response | Error) =>
      new AuthBackofficeClient(
        BASE,
        response instanceof Error ? vi.fn().mockRejectedValue(response) : vi.fn().mockResolvedValue(response)
      ).password('d', 'p', CONTEXT);

    expect(await run(json(401))).toEqual({ kind: 'refused' });
    expect(await run(json(503))).toEqual({ kind: 'unavailable' });
    expect(await run(json(200, { access_token: 'x' }))).toEqual({ kind: 'unavailable' });
    expect(await run(new Error('x'))).toEqual({ kind: 'unavailable' });
  });
});

import { NextRequest } from 'next/server';
import { describe, expect, it, vi } from 'vitest';
import type { LogEvent } from '../lib/log-event';
import type { EvaluateResult } from '../lib/session-service';
import { createProxy, proxy } from '../proxy';

const claims = { sub: 'u-1', exp: 1_790_000_900, roles: ['operator'], amr: ['face', 'pwd'] };

function setup(result: EvaluateResult = { kind: 'valid', claims }) {
  const events: LogEvent[] = [];
  const sessions = { evaluate: vi.fn().mockResolvedValue(result) };
  return { proxy: createProxy({ sessions, log: (event) => events.push(event) }), sessions, events };
}

const get = (path: string, headers: Record<string, string> = {}) =>
  new NextRequest(`http://admin.localhost${path}`, { headers: { host: 'admin.localhost', ...headers } });

describe('proxy : journal et corrélation', () => {
  it('journalise la page servie et propage le X-Correlation-ID reçu', async () => {
    const { proxy, events } = setup();

    const response = await proxy(get('/', { 'x-correlation-id': 'abcdefgh-1234' }));

    expect(response.headers.get('X-Correlation-ID')).toBe('abcdefgh-1234');
    expect(events[0]).toMatchObject({
      service: 'basecamp-backoffice',
      event: 'backoffice.page_served',
      outcome: 'success',
      correlation_id: 'abcdefgh-1234',
    });
  });

  it('génère un identifiant quand celui reçu est invalide', async () => {
    const response = await setup().proxy(get('/', { 'x-correlation-id': 'x' }));

    expect(response.headers.get('X-Correlation-ID')).toMatch(/^[0-9a-f-]{36}$/);
  });
});

describe('proxy : garde de route', () => {
  it.each([
    '/login',
    '/session/identify',
    '/session/face',
    '/session/password',
    '/session/logout',
    '/robots.txt',
  ])('laisse passer %s sans session', async (path) => {
    const { proxy, sessions } = setup({ kind: 'none', reason: 'no_session' });

    expect((await proxy(get(path))).status).toBe(200);
    expect(sessions.evaluate).not.toHaveBeenCalled();
  });

  it('laisse passer une session valide, vérifiée sur le jeton du cookie', async () => {
    const { proxy, sessions } = setup();

    const response = await proxy(get('/', { cookie: 'bo_access=a.b.c' }));

    expect(response.status).toBe(200);
    expect(sessions.evaluate).toHaveBeenCalledWith('a.b.c');
  });

  it('renvoie à la connexion sans session valide, efface le cookie et journalise le motif', async () => {
    const { proxy, events } = setup({ kind: 'none', reason: 'session_expired' });

    const response = await proxy(get('/produits', { cookie: 'bo_access=vieux.jeton.x' }));

    expect(response.status).toBe(307);
    expect(response.headers.get('location')).toBe('http://admin.localhost/login');
    expect(response.headers.getSetCookie().join('\n')).toMatch(/bo_access=;.*Max-Age=0/i);
    expect(events.find((e) => e.event === 'backoffice.access_denied')).toMatchObject({
      outcome: 'denied',
      reason: 'session_expired',
    });
  });

  it.each(['/commandes', '/commandes/00000000-0000-4000-8000-000000000001'])(
    'protège l’écran %s : sans session, retour à la connexion',
    async (path) => {
      const { proxy, sessions } = setup({ kind: 'none', reason: 'no_session' });

      const response = await proxy(get(path));

      expect(response.status).toBe(307);
      expect(response.headers.get('location')).toBe('http://admin.localhost/login');
      expect(sessions.evaluate).toHaveBeenCalledOnce();
    }
  );

  it.each(['/bff/orders', '/bff/orders/00000000-0000-4000-8000-000000000001'])(
    'protège la route %s : 401 JSON sans session',
    async (path) => {
      const { proxy } = setup({ kind: 'none', reason: 'second_factor_missing' });

      const response = await proxy(get(path, { cookie: 'bo_access=a.b.c' }));

      expect(response.status).toBe(401);
    }
  );

  it('un faux cookie « opérateur » ne passe pas', async () => {
    const { proxy } = setup({ kind: 'none', reason: 'bad_signature' });

    expect((await proxy(get('/', { cookie: 'bo_access=faux.jeton.signe' }))).status).toBe(307);
  });

  it('répond 401 JSON aux appels /bff sans session au lieu de rediriger', async () => {
    const { proxy } = setup({ kind: 'none', reason: 'no_session' });

    const response = await proxy(get('/bff/produits'));

    expect(response.status).toBe(401);
    expect(await response.json()).toEqual({ detail: 'Authentification requise.' });
  });

  it('une panne d’auth envoie à la connexion avec le message de service indisponible, sans effacer le cookie', async () => {
    const { proxy } = setup({ kind: 'error', reason: 'auth_unavailable' });

    const response = await proxy(get('/', { cookie: 'bo_access=a.b.c' }));

    expect(response.headers.get('location')).toBe('http://admin.localhost/login?erreur=2');
    expect(response.headers.getSetCookie()).toEqual([]);
  });
});

describe('proxy : assemblage', () => {
  it('le proxy exporté s’appuie sur la session du runtime', async () => {
    vi.spyOn(console, 'log').mockImplementation(() => undefined);
    vi.stubEnv('AUTH_URL', 'http://auth.test:8000');
    vi.stubEnv('SHOP_URL', 'http://shop.test:8000');

    const response = await proxy(get('/login'));

    expect(response.status).toBe(200);
  });
});

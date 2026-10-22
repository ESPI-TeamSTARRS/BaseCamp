import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { NextRequest } from 'next/server';
import { vi } from 'vitest';
import { createProxy } from '../../proxy';
import { handleCatalog } from '../handlers/catalog-handlers';
import { handleFace, handleIdentify, handlePassword } from '../handlers/login-steps';
import { handleLogout } from '../handlers/logout-handler';
import { handleOrders } from '../handlers/order-handlers';
import { buildLogEvent, type LogEvent } from '../log-event';
import type { ShopReply } from '../shop-client';

// Contrat commun des journaux (docs/development/log-event.schema.json), relu ici pour que les
// evenements du back-office restent conformes sans dependance de validation supplementaire.
interface Schema {
  required: string[];
  properties: Record<string, { pattern?: string; enum?: string[] }>;
  description: string;
  version?: string;
}

const schema = JSON.parse(
  readFileSync(path.resolve(__dirname, '../../../../../docs/development/log-event.schema.json'), 'utf8')
) as Schema;

function violations(event: Record<string, unknown>): string[] {
  const problems: string[] = [];
  for (const name of schema.required) if (!(name in event)) problems.push(`manque ${name}`);
  for (const [name, value] of Object.entries(event)) {
    const rule = schema.properties[name];
    if (!rule) {
      problems.push(`champ inconnu ${name}`);
      continue;
    }
    if (rule.pattern && !new RegExp(rule.pattern).test(String(value))) problems.push(`motif ${name}`);
    if (rule.enum && !rule.enum.includes(String(value))) problems.push(`valeur ${name}`);
  }
  if (event.resource_id !== undefined && event.resource_type === undefined)
    problems.push('resource_id sans resource_type');
  if ((event.outcome === 'success') === 'reason' in event) problems.push('reason incoherent');
  return problems;
}

const base = { correlationId: 'b3a9d7e1-55c4-4d0a-8f21-0c9e4a6d7f33' };

describe('contrat des journaux : backoffice.order_view', () => {
  it('une consultation réussie respecte le schéma commun', () => {
    const event = buildLogEvent({
      ...base,
      event: 'backoffice.order_view',
      outcome: 'success',
      durationMs: 12,
      resource: { type: 'order', id: '00000000-0000-4000-8000-000000000001' },
      actor: { type: 'user', id: '0123456789abcdef' },
      attributes: { status: 200 },
    });

    expect(violations({ ...event })).toEqual([]);
  });

  it('un refus respecte le schéma commun et porte un motif', () => {
    const event = buildLogEvent({
      ...base,
      event: 'backoffice.order_view',
      outcome: 'denied',
      reason: 'not_found',
      resource: { type: 'order', id: 'abc' },
      actor: { type: 'user', id: '0123456789abcdef' },
    });

    expect(violations({ ...event })).toEqual([]);
  });

  it('détecte un champ hors contrat', () => {
    expect(
      violations({ ...buildLogEvent({ ...base, event: 'a.b', outcome: 'success' }), email: 'x' })
    ).toEqual(['champ inconnu email']);
  });

  it('le schéma nomme le back-office parmi les émetteurs', () => {
    expect(schema.description).toContain('backoffice');
  });
});

// Evenements reellement produits par chaque gestionnaire du back-office, ecrits comme en production
// (une ligne JSON), puis valides contre le schema commun.
describe('contrat des journaux : tous les événements du back-office', () => {
  const challenge = 'defi-opaque-0123456789abcdef';
  const orderId = '00000000-0000-4000-8000-000000000001';
  const claims = {
    sub: '0b6c1a52-7a3e-4f0e-9b57-3f2d8c6a1e90',
    exp: 9_999_999_999,
    roles: ['operator'],
    amr: ['face'],
  };
  const cookie = { cookie: 'bo_access=a.b.c', host: 'admin.localhost', 'sec-fetch-site': 'same-origin' };

  function post(path: string, body: unknown): Request {
    return new Request(`http://backoffice:3000${path}`, {
      method: 'POST',
      headers: { ...cookie, 'content-type': 'application/json', 'x-correlation-id': base.correlationId },
      body: JSON.stringify(body),
    });
  }

  function get(path: string, headers: Record<string, string> = cookie): Request {
    return new Request(`http://backoffice:3000${path}`, {
      headers: { ...headers, 'x-correlation-id': base.correlationId },
    });
  }

  async function collect(): Promise<LogEvent[]> {
    const lines: string[] = [];
    const log = (event: LogEvent) => lines.push(JSON.stringify(event));
    const ok = { ok: true, status: 200, data: {} } as const;
    const failures: ShopReply[] = [
      { ok: false, failure: 'not_found', status: 404 },
      { ok: false, failure: 'unavailable', status: 0 },
    ];
    const shop = (reply: ShopReply) => ({ call: async () => reply });
    const sessions = (kind: 'valid' | 'none') => ({
      evaluate: async () =>
        kind === 'valid' ? ({ kind, claims } as const) : ({ kind, reason: 'second_factor_missing' } as const),
    });
    for (const reply of [ok, ...failures]) {
      const deps = { shop: shop(reply), sessions: sessions('valid'), pseudonymKey: 'cle', log };
      await handleOrders(get(`/bff/orders/${orderId}`), 'get', orderId, deps);
      await handleOrders(get('/bff/orders?limit=20'), 'list', undefined, deps);
      await handleCatalog(get('/bff/products'), 'list', undefined, { shop: shop(reply), log });
    }
    await handleOrders(get('/bff/orders'), 'list', undefined, {
      shop: shop(ok),
      sessions: sessions('none'),
      pseudonymKey: 'cle',
      log,
    });
    const client = {
      identify: vi.fn().mockResolvedValue({ kind: 'ok', challengeId: challenge, expiresIn: 120 }),
      face: vi.fn().mockResolvedValueOnce({ kind: 'ok' }).mockResolvedValue({ kind: 'refused' }),
      password: vi
        .fn()
        .mockResolvedValueOnce({ kind: 'ok', accessToken: 'a.b.c', expiresIn: 900 })
        .mockResolvedValue({ kind: 'refused' }),
    };
    const steps = { client: client as never, pseudonymKey: 'cle', log };
    await handleIdentify(post('/session/identify', { email: 'operateur@example.test' }), steps);
    await handleFace(post('/session/face', { challenge_id: challenge, images: ['AAAA'] }), steps);
    await handleFace(post('/session/face', { challenge_id: challenge, images: ['AAAA'] }), steps);
    await handlePassword(post('/session/password', { challenge_id: challenge, password: 'x' }), steps);
    await handlePassword(post('/session/password', { challenge_id: challenge, password: 'x' }), steps);
    handleLogout(post('/session/logout', {}), { log });
    handleLogout(new Request('http://backoffice:3000/session/logout', { method: 'POST' }), { log });
    const proxy = createProxy({
      sessions: { evaluate: async () => ({ kind: 'valid', claims }) },
      log: (event) => lines.push(JSON.stringify(event)),
    });
    await proxy(
      new NextRequest('http://admin.localhost/commandes', { headers: { host: 'admin.localhost' } })
    );
    const denied = createProxy({
      sessions: { evaluate: async () => ({ kind: 'none', reason: 'no_session' }) },
      log: (event) => lines.push(JSON.stringify(event)),
    });
    await denied(
      new NextRequest('http://admin.localhost/commandes', { headers: { host: 'admin.localhost' } })
    );
    return lines.map((line) => JSON.parse(line) as LogEvent);
  }

  it('chaque ligne émise respecte le schéma commun', async () => {
    const events = await collect();

    expect(events.length).toBeGreaterThan(15);
    for (const event of events) expect(violations({ ...event }), event.event).toEqual([]);
    const names = new Set(events.map((event) => event.event));
    for (const expected of [
      'backoffice.login_identify',
      'backoffice.login_face',
      'backoffice.login_password',
      'backoffice.logout',
      'backoffice.page_served',
      'backoffice.access_denied',
      'backoffice.catalog_list',
      'backoffice.orders_list',
      'backoffice.order_view',
    ])
      expect(names, expected).toContain(expected);
  });

  it('aucun événement ne porte d’e-mail, de jeton ni de défi', async () => {
    const raw = JSON.stringify(await collect());

    for (const secret of ['operateur@example.test', 'a.b.c', challenge, '0b6c1a52-7a3e-4f0e']) {
      expect(raw).not.toContain(secret);
    }
  });

  it('le schéma porte un numéro de version incrémenté pour cette extension', () => {
    expect(schema.version).toBe('1.2.0');
  });
});

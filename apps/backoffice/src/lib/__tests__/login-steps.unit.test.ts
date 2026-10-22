import { describe, expect, it, vi } from 'vitest';
import { handleFace, handleIdentify, handlePassword } from '../handlers/login-steps';
import type { LogEvent } from '../log-event';

const CHALLENGE = 'defi-opaque-0123456789abcdef';
const SECRET_VALUE = 'mot-de-passe-de-test';

function post(path: string, body: unknown, headers: Record<string, string> = {}): Request {
  return new Request(`http://backoffice:3000${path}`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      host: 'mercure.localhost:8260',
      'sec-fetch-site': 'same-origin',
      'x-forwarded-for': '203.0.113.7',
      ...headers,
    },
    body: typeof body === 'string' ? body : JSON.stringify(body),
  });
}

function setup(overrides: Record<string, unknown> = {}) {
  const events: LogEvent[] = [];
  const client = {
    identify: vi.fn().mockResolvedValue({ kind: 'ok', challengeId: CHALLENGE, expiresIn: 120 }),
    face: vi.fn().mockResolvedValue({ kind: 'ok' }),
    password: vi.fn().mockResolvedValue({ kind: 'ok', accessToken: 'a.b.c', expiresIn: 900 }),
    ...overrides,
  };
  return {
    client,
    events,
    deps: {
      client: client as never,
      pseudonymKey: 'cle-de-test',
      log: (event: LogEvent) => events.push(event),
    },
  };
}

describe('handleIdentify', () => {
  it('rend le défi à usage unique et transmet l’adresse source', async () => {
    const { deps, client } = setup();

    const response = await handleIdentify(
      post('/session/identify', { email: 'Op@Example.org' }, { 'x-correlation-id': 'corr-12345678' }),
      deps
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ challenge_id: CHALLENGE, expires_in: 120 });
    expect(client.identify).toHaveBeenCalledWith('Op@Example.org', {
      correlationId: 'corr-12345678',
      forwardedFor: '203.0.113.7',
    });
  });

  it.each([
    {},
    { email: 3 },
    { email: 'pas-une-adresse' },
    { email: `${'a'.repeat(300)}@b.c` },
    'pas du json',
    [],
  ])('refuse un corps invalide (%j) sans appeler auth', async (body) => {
    const { deps, client } = setup();

    const response = await handleIdentify(post('/session/identify', body), deps);

    expect(response.status).toBe(422);
    expect(client.identify).not.toHaveBeenCalled();
  });

  it('journalise avec une empreinte, jamais l’adresse', async () => {
    const { deps, events } = setup();

    await handleIdentify(post('/session/identify', { email: 'op@example.org' }), deps);

    expect(events[0]).toMatchObject({ event: 'backoffice.login_identify', outcome: 'success' });
    expect(events[0].attributes?.email_hash).toMatch(/^[0-9a-f]{16}$/);
    expect(JSON.stringify(events)).not.toContain('example.org');
  });

  it('une panne d’auth est un 503 générique', async () => {
    const { deps, events } = setup({ identify: vi.fn().mockResolvedValue({ kind: 'unavailable' }) });

    const response = await handleIdentify(post('/session/identify', { email: 'op@example.org' }), deps);

    expect(response.status).toBe(503);
    expect(events[0]).toMatchObject({ outcome: 'error', reason: 'auth_unavailable' });
  });

  it('refuse une requête venue d’un autre site', async () => {
    const { deps, client } = setup();

    const response = await handleIdentify(
      post('/session/identify', { email: 'op@example.org' }, { 'sec-fetch-site': 'cross-site' }),
      deps
    );

    expect(response.status).toBe(403);
    expect(client.identify).not.toHaveBeenCalled();
  });
});

describe('handleFace', () => {
  const body = { challenge_id: CHALLENGE, images: ['aGVsbG8='] };

  it('relaie les images et rend le résultat', async () => {
    const { deps, client } = setup();

    const response = await handleFace(post('/session/face', body), deps);

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ face_ok: true });
    expect(client.face).toHaveBeenCalledWith(
      CHALLENGE,
      ['aGVsbG8='],
      expect.objectContaining({ forwardedFor: '203.0.113.7' })
    );
  });

  it('un visage refusé est un 401 générique, des images invalides un 422', async () => {
    const refused = setup({ face: vi.fn().mockResolvedValue({ kind: 'refused' }) });
    const invalid = setup({ face: vi.fn().mockResolvedValue({ kind: 'invalid_images' }) });

    const one = await handleFace(post('/session/face', body), refused.deps);
    const two = await handleFace(post('/session/face', body), invalid.deps);

    expect([one.status, await one.json()]).toEqual([401, { detail: 'Identifiants invalides.' }]);
    expect([two.status, await two.json()]).toEqual([422, { detail: 'Image invalide.' }]);
    expect(refused.events[0]).toMatchObject({ outcome: 'denied', reason: 'face_refused' });
  });

  it.each([
    {},
    { challenge_id: 'court', images: ['aGVsbG8='] },
    { challenge_id: CHALLENGE, images: [] },
    { challenge_id: CHALLENGE, images: ['a', 'b', 'c', 'd'] },
    { challenge_id: CHALLENGE, images: [3] },
    { challenge_id: CHALLENGE, images: ['x'.repeat(1_500_000)] },
    { challenge_id: CHALLENGE, images: ['pas du base64 !'] },
  ])('refuse un corps invalide sans appeler auth', async (invalid) => {
    const { deps, client } = setup();

    const response = await handleFace(post('/session/face', invalid), deps);

    expect(response.status).toBe(422);
    expect(client.face).not.toHaveBeenCalled();
  });

  it('refuse un corps de plus de 5 Mio', async () => {
    const { deps, client } = setup();

    const response = await handleFace(
      post('/session/face', body, { 'content-length': String(6 * 1024 * 1024) }),
      deps
    );

    expect(response.status).toBe(413);
    expect(client.face).not.toHaveBeenCalled();
  });
});

describe('handlePassword', () => {
  const body = { challenge_id: CHALLENGE, password: SECRET_VALUE };

  it('pose le cookie HttpOnly de session et ne renvoie jamais le jeton', async () => {
    const { deps } = setup();

    const response = await handlePassword(post('/session/password', body), deps);

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ ok: true });
    const cookies = response.headers.getSetCookie().join('\n');
    expect(cookies).toMatch(/bo_access=a\.b\.c;.*Max-Age=900.*HttpOnly.*SameSite=strict/i);
    expect(cookies).not.toMatch(/Secure/);
  });

  it('pose Secure derrière HTTPS', async () => {
    const response = await handlePassword(
      post('/session/password', body, { 'x-forwarded-proto': 'https' }),
      setup().deps
    );

    expect(response.headers.getSetCookie().every((line) => /Secure/i.test(line))).toBe(true);
  });

  it('un refus ne pose aucun cookie et reste générique', async () => {
    const { deps, events } = setup({ password: vi.fn().mockResolvedValue({ kind: 'refused' }) });

    const response = await handlePassword(post('/session/password', body), deps);

    expect([response.status, await response.json()]).toEqual([401, { detail: 'Identifiants invalides.' }]);
    expect(response.headers.getSetCookie()).toEqual([]);
    expect(events[0]).toMatchObject({
      event: 'backoffice.login_password',
      outcome: 'denied',
      reason: 'wrong_password',
    });
  });

  it('une panne d’auth est un 503 sans cookie', async () => {
    const { deps } = setup({ password: vi.fn().mockResolvedValue({ kind: 'unavailable' }) });

    const response = await handlePassword(post('/session/password', body), deps);

    expect(response.status).toBe(503);
    expect(response.headers.getSetCookie()).toEqual([]);
  });

  it('ne journalise ni mot de passe, ni jeton, ni identifiant de défi', async () => {
    const { deps, events } = setup();

    await handlePassword(post('/session/password', body), deps);
    await handleFace(post('/session/face', { challenge_id: CHALLENGE, images: ['aGVsbG8='] }), deps);

    const dumped = JSON.stringify(events);
    expect(dumped).not.toContain(SECRET_VALUE);
    expect(dumped).not.toContain('a.b.c');
    expect(dumped).not.toContain(CHALLENGE);
  });

  it.each([
    {},
    { challenge_id: CHALLENGE },
    { challenge_id: CHALLENGE, password: '' },
    { challenge_id: CHALLENGE, password: 'x'.repeat(300) },
    { challenge_id: 'x', password: 'p' },
  ])('refuse un corps invalide sans appeler auth', async (invalid) => {
    const { deps, client } = setup();

    expect((await handlePassword(post('/session/password', invalid), deps)).status).toBe(422);
    expect(client.password).not.toHaveBeenCalled();
  });
});

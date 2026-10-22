import { afterEach, describe, expect, it, vi } from 'vitest';
import { identify, submitFace, submitPassword } from '../login-api';

function respond(status: number, body: unknown = {}): void {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ status, ok: status >= 200 && status < 300, json: async () => body })
  );
}

afterEach(() => vi.unstubAllGlobals());

describe('identify', () => {
  it('relaie le défi reçu', async () => {
    respond(200, { challenge_id: 'abc', expires_in: 120 });
    expect(await identify('a@b.fr')).toEqual({ kind: 'ok', challengeId: 'abc', expiresIn: 120 });
    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('/session/identify');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ email: 'a@b.fr' });
    expect(init.credentials).toBe('same-origin');
  });

  it('signale une erreur sur une réponse inattendue ou un réseau coupé', async () => {
    respond(500);
    expect(await identify('a@b.fr')).toEqual({ kind: 'error' });
    respond(200, { nope: true });
    expect(await identify('a@b.fr')).toEqual({ kind: 'error' });
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('down')));
    expect(await identify('a@b.fr')).toEqual({ kind: 'error' });
  });
});

describe('submitFace', () => {
  it('visage accepté sur 200', async () => {
    respond(200, { face_ok: true });
    expect(await submitFace('abc', ['i1', 'i2'])).toBe('accepted');
    const init = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][1];
    expect(JSON.parse(init.body)).toEqual({ challenge_id: 'abc', images: ['i1', 'i2'] });
  });

  it('visage refusé sur 401, image illisible sur 422, erreur sinon', async () => {
    respond(401);
    expect(await submitFace('abc', ['i'])).toBe('refused');
    respond(422);
    expect(await submitFace('abc', ['i'])).toBe('invalid_image');
    respond(409);
    expect(await submitFace('abc', ['i'])).toBe('error');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('down')));
    expect(await submitFace('abc', ['i'])).toBe('error');
  });
});

describe('submitPassword', () => {
  it('succès sur 200, refus sur 401, erreur sinon', async () => {
    respond(200);
    expect(await submitPassword('abc', 'secret')).toBe('success');
    respond(401);
    expect(await submitPassword('abc', 'secret')).toBe('refused');
    respond(502);
    expect(await submitPassword('abc', 'secret')).toBe('error');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('down')));
    expect(await submitPassword('abc', 'secret')).toBe('error');
  });
});

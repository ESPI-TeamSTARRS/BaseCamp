import { describe, expect, it, vi } from 'vitest';
import { JwksCache } from '../jwks-cache';
import { newKey } from './token-fixtures';

function setup(keys = [newKey('kid-1')]) {
  let now = 1_000_000;
  const fetchImpl = vi.fn(
    async () => new Response(JSON.stringify({ keys: keys.map((k) => k.jwk) }), { status: 200 })
  );
  const cache = new JwksCache(
    'http://auth:8000/.well-known/jwks.json',
    fetchImpl as never,
    () => now,
    300_000,
    10_000
  );
  return { cache, fetchImpl, keys, advance: (ms: number) => (now += ms) };
}

describe('JwksCache', () => {
  it('lit les clés une fois et les garde 5 minutes', async () => {
    const { cache, fetchImpl, advance } = setup();

    expect(await cache.keyFor('kid-1')).not.toBeNull();
    expect(await cache.keyFor('kid-1')).not.toBeNull();
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    advance(300_001);
    await cache.keyFor('kid-1');
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it('relit les clés pour un kid inconnu, mais pas plus d’une fois toutes les 10 secondes', async () => {
    const { cache, fetchImpl, advance } = setup();

    expect(await cache.keyFor('inconnu')).toBeNull();
    expect(await cache.keyFor('inconnu')).toBeNull();
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    advance(10_001);
    expect(await cache.keyFor('inconnu')).toBeNull();
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it('garde les anciennes clés quand auth est arrêté, et signale l’indisponibilité sinon', async () => {
    const { cache, advance } = setup();
    await cache.keyFor('kid-1');
    const down = new JwksCache(
      'http://auth',
      (async () => {
        throw new Error('refusé');
      }) as never,
      () => 0,
      300_000,
      10_000
    );

    advance(400_000);
    expect(await cache.keyFor('kid-1')).not.toBeNull();
    await expect(down.keyFor('kid-1')).rejects.toThrow('jwks_unavailable');
  });

  it('refuse un JWKS illisible ou une clé qui n’est pas Ed25519', async () => {
    const bad = new JwksCache(
      'http://auth',
      (async () => new Response('{"keys":[{"kty":"RSA","kid":"k"}]}')) as never,
      () => 0,
      1,
      1
    );
    const garbage = new JwksCache(
      'http://auth',
      (async () => new Response('pas du json')) as never,
      () => 0,
      1,
      1
    );

    expect(await bad.keyFor('k')).toBeNull();
    await expect(garbage.keyFor('k')).rejects.toThrow('jwks_unavailable');
  });
});

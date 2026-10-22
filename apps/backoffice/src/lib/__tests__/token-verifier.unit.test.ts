import { describe, expect, it } from 'vitest';
import { JwksCache } from '../jwks-cache';
import { TokenVerifier } from '../token-verifier';
import { AUDIENCE, ISSUER, NOW_S, newKey, signToken } from './token-fixtures';

function setup(down = false) {
  const key = newKey();
  const jwks = new JwksCache(
    'http://auth',
    (async () => {
      if (down) throw new Error('arrêté');
      return new Response(JSON.stringify({ keys: [key.jwk] }));
    }) as never,
    () => NOW_S * 1000,
    300_000,
    10_000
  );
  return { key, verifier: new TokenVerifier(jwks, ISSUER, AUDIENCE, () => NOW_S * 1000) };
}

describe('TokenVerifier', () => {
  it('accepte un jeton d’opérateur signé par auth avec le second facteur visage', async () => {
    const { key, verifier } = setup();

    const result = await verifier.verify(signToken(key));

    expect(result).toEqual({
      kind: 'ok',
      claims: expect.objectContaining({ roles: ['operator'], amr: ['face', 'pwd'], exp: NOW_S + 900 }),
    });
  });

  it.each([
    ['expired', { exp: NOW_S - 31 }],
    ['wrong_issuer', { iss: 'autre' }],
    ['wrong_audience', { aud: 'autre' }],
    ['not_a_client_token', { token_use: 'service' }],
    ['not_operator', { roles: ['customer'] }],
    ['not_operator', { roles: 'operator' }],
    ['second_factor_missing', { amr: ['pwd'] }],
    ['second_factor_missing', { amr: undefined }],
    ['second_factor_missing', { amr: 'face' }],
  ])('refuse (%s) un jeton valide en signature mais non conforme', async (reason, claims) => {
    const { key, verifier } = setup();

    expect(await verifier.verify(signToken(key, claims))).toEqual({ kind: 'invalid', reason });
  });

  it('tolère 30 secondes d’écart d’horloge', async () => {
    const { key, verifier } = setup();

    expect((await verifier.verify(signToken(key, { exp: NOW_S - 30 }))).kind).toBe('ok');
  });

  it('refuse une signature fausse, un corps altéré et une clé étrangère', async () => {
    const { key, verifier } = setup();
    const token = signToken(key);
    const [head, body, signature] = token.split('.');
    const altered = Buffer.from(
      JSON.stringify({ ...JSON.parse(Buffer.from(body, 'base64url').toString()), roles: ['operator', 'x'] })
    ).toString('base64url');
    const stranger = signToken(newKey('kid-1'));

    expect(await verifier.verify(`${head}.${altered}.${signature}`)).toEqual({
      kind: 'invalid',
      reason: 'bad_signature',
    });
    expect(await verifier.verify(stranger)).toEqual({ kind: 'invalid', reason: 'bad_signature' });
    expect(await verifier.verify(`${head}.${body}.${signature.slice(2)}AA`)).toEqual({
      kind: 'invalid',
      reason: 'bad_signature',
    });
  });

  it('refuse un algorithme autre qu’EdDSA, y compris none, et un kid inconnu ou absent', async () => {
    const { key, verifier } = setup();

    expect(await verifier.verify(signToken(key, {}, { alg: 'none' }))).toEqual({
      kind: 'invalid',
      reason: 'bad_algorithm',
    });
    expect(await verifier.verify(signToken(key, {}, { alg: 'HS256' }))).toEqual({
      kind: 'invalid',
      reason: 'bad_algorithm',
    });
    expect(await verifier.verify(signToken(key, {}, { kid: 'inconnu' }))).toEqual({
      kind: 'invalid',
      reason: 'unknown_key',
    });
    expect(await verifier.verify(signToken(key, {}, { kid: undefined }))).toEqual({
      kind: 'invalid',
      reason: 'unknown_key',
    });
  });

  it('refuse tout ce qui ne ressemble pas à un jeton', async () => {
    const { verifier } = setup();

    for (const bad of ['', 'abc', 'a.b', 'a.b.c.d', '!!!.!!!.!!!']) {
      expect(await verifier.verify(bad)).toEqual({ kind: 'invalid', reason: 'malformed' });
    }
  });

  it('signale une indisponibilité d’auth sans clé en cache, jamais un accès', async () => {
    const { key } = setup();
    const { verifier } = setup(true);

    expect(await verifier.verify(signToken(key))).toEqual({ kind: 'error', reason: 'auth_unavailable' });
  });
});

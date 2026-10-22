// Cles et jetons de test au format d'`auth` : EdDSA (Ed25519), `kid` dans l'en-tete, JWKS publie.
import { generateKeyPairSync, sign, type KeyObject } from 'node:crypto';

export const ISSUER = 'basecamp-auth';
export const AUDIENCE = 'basecamp-client-api';
export const NOW_S = 1_790_000_000;

export interface TestKey {
  kid: string;
  privateKey: KeyObject;
  jwk: { kty: string; crv: string; x: string; kid: string; alg: string; use: string };
}

export function newKey(kid = 'kid-1'): TestKey {
  const { publicKey, privateKey } = generateKeyPairSync('ed25519');
  const exported = publicKey.export({ format: 'jwk' }) as { kty: string; crv: string; x: string };
  return { kid, privateKey, jwk: { ...exported, kid, alg: 'EdDSA', use: 'sig' } };
}

const part = (value: unknown) => Buffer.from(JSON.stringify(value)).toString('base64url');

export function signToken(
  key: TestKey,
  overrides: Record<string, unknown> = {},
  header: Record<string, unknown> = {}
): string {
  const claims = {
    iss: ISSUER,
    aud: AUDIENCE,
    sub: '0b6b1f2e-6c52-4d3b-8a52-1d6f7a9b2c10',
    roles: ['operator'],
    amr: ['face', 'pwd'],
    token_use: 'client',
    iat: NOW_S - 60,
    exp: NOW_S + 900,
    jti: 'jti-1',
    ...overrides,
  };
  const head = { alg: 'EdDSA', typ: 'JWT', kid: key.kid, ...header };
  const input = `${part(head)}.${part(claims)}`;
  return `${input}.${sign(null, Buffer.from(input), key.privateKey).toString('base64url')}`;
}

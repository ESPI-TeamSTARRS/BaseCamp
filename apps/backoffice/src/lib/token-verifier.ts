import { verify } from 'node:crypto';
import type { JwksCache } from './jwks-cache';

const OPERATOR_ROLE = 'operator';
const SECOND_FACTOR = 'face';
const CLOCK_TOLERANCE_SECONDS = 30;
const SEGMENTS = 3;

export interface VerifiedClaims {
  sub: string;
  exp: number;
  roles: string[];
  amr: string[];
}

export type VerifyResult =
  | { kind: 'ok'; claims: VerifiedClaims }
  | {
      kind: 'invalid';
      reason:
        | 'malformed'
        | 'bad_algorithm'
        | 'unknown_key'
        | 'bad_signature'
        | 'wrong_issuer'
        | 'wrong_audience'
        | 'not_a_client_token'
        | 'expired'
        | 'not_operator'
        | 'second_factor_missing';
    }
  | { kind: 'error'; reason: 'auth_unavailable' };

const textList = (value: unknown): string[] =>
  Array.isArray(value) && value.every((item) => typeof item === 'string') ? (value as string[]) : [];

function decode(part: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(Buffer.from(part, 'base64url').toString('utf8'));
    return typeof value === 'object' && value !== null && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

/** Verifie un jeton d'acces d'`auth` : signature EdDSA par JWKS, emetteur, audience, expiration, role et second facteur. */
export class TokenVerifier {
  constructor(
    private readonly jwks: JwksCache,
    private readonly issuer: string,
    private readonly audience: string,
    private readonly nowMs: () => number = Date.now
  ) {}

  async verify(token: string): Promise<VerifyResult> {
    const parts = token.split('.');
    if (parts.length !== SEGMENTS) return { kind: 'invalid', reason: 'malformed' };
    const header = decode(parts[0]);
    const claims = decode(parts[1]);
    if (header === null || claims === null) return { kind: 'invalid', reason: 'malformed' };
    if (header.alg !== 'EdDSA') return { kind: 'invalid', reason: 'bad_algorithm' };
    if (typeof header.kid !== 'string') return { kind: 'invalid', reason: 'unknown_key' };
    let key;
    try {
      key = await this.jwks.keyFor(header.kid);
    } catch {
      return { kind: 'error', reason: 'auth_unavailable' };
    }
    if (key === null) return { kind: 'invalid', reason: 'unknown_key' };
    const signed = Buffer.from(`${parts[0]}.${parts[1]}`);
    let genuine = false;
    try {
      genuine = verify(null, signed, key, Buffer.from(parts[2], 'base64url'));
    } catch {
      genuine = false;
    }
    if (!genuine) return { kind: 'invalid', reason: 'bad_signature' };
    return this.check(claims);
  }

  private check(claims: Record<string, unknown>): VerifyResult {
    if (claims.iss !== this.issuer) return { kind: 'invalid', reason: 'wrong_issuer' };
    const audiences = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
    if (!audiences.includes(this.audience)) return { kind: 'invalid', reason: 'wrong_audience' };
    if (claims.token_use !== 'client') return { kind: 'invalid', reason: 'not_a_client_token' };
    if (typeof claims.exp !== 'number' || this.nowMs() / 1000 > claims.exp + CLOCK_TOLERANCE_SECONDS) {
      return { kind: 'invalid', reason: 'expired' };
    }
    const roles = textList(claims.roles);
    if (!roles.includes(OPERATOR_ROLE) || typeof claims.sub !== 'string')
      return { kind: 'invalid', reason: 'not_operator' };
    const amr = textList(claims.amr);
    if (!amr.includes(SECOND_FACTOR)) return { kind: 'invalid', reason: 'second_factor_missing' };
    return { kind: 'ok', claims: { sub: claims.sub, exp: claims.exp, roles, amr } };
  }
}

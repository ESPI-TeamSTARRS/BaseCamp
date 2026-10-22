import type { TokenVerifier, VerifiedClaims, VerifyResult } from './token-verifier';

export type EvaluateResult =
  | { kind: 'valid'; claims: VerifiedClaims }
  | { kind: 'none'; reason: string }
  | { kind: 'error'; reason: 'auth_unavailable' };

/** Decide si un cookie de session ouvre le back-office : jeton d'operateur signe par auth, avec le visage. */
export class SessionService {
  constructor(private readonly verifier: Pick<TokenVerifier, 'verify'>) {}

  async evaluate(accessToken: string | undefined): Promise<EvaluateResult> {
    if (accessToken === undefined) return { kind: 'none', reason: 'no_session' };
    const result: VerifyResult = await this.verifier.verify(accessToken);
    if (result.kind === 'ok') return { kind: 'valid', claims: result.claims };
    if (result.kind === 'error') return result;
    return { kind: 'none', reason: result.reason === 'expired' ? 'session_expired' : result.reason };
  }
}

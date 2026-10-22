import { describe, expect, it, vi } from 'vitest';
import { SessionService } from '../session-service';
import type { VerifyResult } from '../token-verifier';

const claims = { sub: 'u-1', exp: 1_790_000_900, roles: ['operator'], amr: ['face', 'pwd'] };

function service(result: VerifyResult) {
  const verifier = { verify: vi.fn().mockResolvedValue(result) };
  return { verifier, sessions: new SessionService(verifier as never) };
}

describe('SessionService.evaluate', () => {
  it('une session au jeton vérifié est valide', async () => {
    const { verifier, sessions } = service({ kind: 'ok', claims });

    expect(await sessions.evaluate('a.b.c')).toEqual({ kind: 'valid', claims });
    expect(verifier.verify).toHaveBeenCalledWith('a.b.c');
  });

  it('sans cookie, il n’y a pas de session et rien n’est vérifié', async () => {
    const { verifier, sessions } = service({ kind: 'ok', claims });

    expect(await sessions.evaluate(undefined)).toEqual({ kind: 'none', reason: 'no_session' });
    expect(verifier.verify).not.toHaveBeenCalled();
  });

  it('un jeton expiré est une session expirée, les autres refus gardent leur motif', async () => {
    expect(await service({ kind: 'invalid', reason: 'expired' }).sessions.evaluate('x')).toEqual({
      kind: 'none',
      reason: 'session_expired',
    });
    expect(await service({ kind: 'invalid', reason: 'bad_signature' }).sessions.evaluate('x')).toEqual({
      kind: 'none',
      reason: 'bad_signature',
    });
    expect(
      await service({ kind: 'invalid', reason: 'second_factor_missing' }).sessions.evaluate('x')
    ).toEqual({ kind: 'none', reason: 'second_factor_missing' });
  });

  it('une panne d’auth sans clé est une erreur, jamais un accès', async () => {
    expect(await service({ kind: 'error', reason: 'auth_unavailable' }).sessions.evaluate('x')).toEqual({
      kind: 'error',
      reason: 'auth_unavailable',
    });
  });
});

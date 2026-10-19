import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getClientIp, rateLimit } from '../rate-limit';

describe('rateLimit', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('autorise les requetes sous la limite', () => {
    expect(rateLimit('k-under', 2).allowed).toBe(true);
    expect(rateLimit('k-under', 2).allowed).toBe(true);
  });

  it('bloque au-dela de la limite et indique le delai de reessai', () => {
    rateLimit('k-over', 1);
    const result = rateLimit('k-over', 1);
    expect(result.allowed).toBe(false);
    expect(result.retryAfterSeconds).toBeGreaterThan(0);
  });

  it('libere la cle une fois la fenetre ecoulee', () => {
    rateLimit('k-window', 1);
    vi.advanceTimersByTime(61_000);
    expect(rateLimit('k-window', 1).allowed).toBe(true);
  });
});

describe('getClientIp', () => {
  it('lit la premiere IP de X-Forwarded-For', () => {
    const req = new Request('http://x', { headers: { 'x-forwarded-for': '1.2.3.4, 5.6.7.8' } });
    expect(getClientIp(req)).toBe('1.2.3.4');
  });

  it('retourne unknown sans en-tete', () => {
    expect(getClientIp(new Request('http://x'))).toBe('unknown');
  });
});

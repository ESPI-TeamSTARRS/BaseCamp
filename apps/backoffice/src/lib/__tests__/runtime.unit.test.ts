import { describe, expect, it } from 'vitest';
import { runtime } from '../runtime';

describe('runtime', () => {
  it('assemble la session, le client des trois temps et la clé de pseudonymisation, une seule fois', () => {
    const first = runtime({ AUTH_URL: 'http://auth.test:8000', LOG_PSEUDONYM_KEY: 'cle-de-test' });
    const second = runtime({ AUTH_URL: 'http://autre:1', LOG_PSEUDONYM_KEY: 'autre-cle' });

    expect(first.pseudonymKey).toBe('cle-de-test');
    expect(second).toBe(first);
    expect(first.sessions).toBeDefined();
    expect(first.client).toBeDefined();
  });
});

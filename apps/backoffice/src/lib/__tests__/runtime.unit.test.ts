import { describe, expect, it } from 'vitest';
import { buildRuntime, runtime } from '../runtime';

const ENV = { AUTH_URL: 'http://auth.test:8000', SHOP_URL: 'http://shop.test:8000' };

describe('runtime', () => {
  it('assemble la session, les clients et la clé de pseudonymisation, une seule fois', () => {
    const first = runtime({ ...ENV, LOG_PSEUDONYM_KEY: 'cle-de-test' });
    const second = runtime({ ...ENV, AUTH_URL: 'http://autre:1', LOG_PSEUDONYM_KEY: 'autre-cle' });

    expect(first.pseudonymKey).toBe('cle-de-test');
    expect(second).toBe(first);
    expect(first.sessions).toBeDefined();
    expect(first.client).toBeDefined();
    expect(first.shop).toBeDefined();
  });

  it('tire une clé éphémère sans LOG_PSEUDONYM_KEY', () => {
    expect(buildRuntime(ENV).pseudonymKey).toMatch(/^[0-9a-f]{32}$/);
  });

  it.each(['AUTH_URL', 'SHOP_URL'])('refuse de démarrer sans %s, avec un message clair', (name) => {
    expect(() => buildRuntime({ ...ENV, [name]: undefined })).toThrow(`${name} est obligatoire`);
  });
});

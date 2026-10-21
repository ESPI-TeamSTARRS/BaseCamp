import { afterEach, describe, expect, it, vi } from 'vitest';
import { clearSession, getAccessToken, setSession, subscribeSession } from '../session-store';

afterEach(() => {
  clearSession();
  vi.unstubAllGlobals();
});

describe('session-store', () => {
  it('garde le jeton d acces en memoire tant qu il est valide', () => {
    setSession('jeton', 900, 1_000);

    expect(getAccessToken(1_000)).toBe('jeton');
    expect(getAccessToken(1_000 + 899_000)).toBe('jeton');
  });

  it('oublie le jeton a son expiration', () => {
    setSession('jeton', 900, 1_000);

    expect(getAccessToken(1_000 + 900_000)).toBeNull();
  });

  it('commence sans session et s efface sur demande', () => {
    expect(getAccessToken()).toBeNull();
    setSession('jeton', 900);
    clearSession();

    expect(getAccessToken()).toBeNull();
  });

  it('ne touche jamais au stockage du navigateur', () => {
    const storage = { getItem: vi.fn(), setItem: vi.fn(), removeItem: vi.fn(), clear: vi.fn() };
    vi.stubGlobal('localStorage', storage);
    vi.stubGlobal('sessionStorage', storage);
    vi.stubGlobal('document', { cookie: '' });

    setSession('jeton', 900);
    getAccessToken();
    clearSession();

    expect(storage.setItem).not.toHaveBeenCalled();
    expect(storage.getItem).not.toHaveBeenCalled();
    expect((globalThis as { document: { cookie: string } }).document.cookie).toBe('');
  });

  it('previent les abonnes a chaque changement et permet de se desabonner', () => {
    const listener = vi.fn();
    const unsubscribe = subscribeSession(listener);

    setSession('jeton', 900);
    clearSession();
    unsubscribe();
    setSession('autre', 900);

    expect(listener).toHaveBeenCalledTimes(2);
  });
});

import { afterEach, describe, expect, it, vi } from 'vitest';
import { submitLogin, validateLogin } from '../login-flow';
import { clearSession, getAccessToken } from '../session-store';

const GOOD = { email: 'camille@example.com', password: 'sentier-du-mont-blanc' };

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

afterEach(() => clearSession());

describe('validateLogin', () => {
  it('normalise l email et accepte n importe quel mot de passe non vide', () => {
    expect(validateLogin({ email: ' Camille@Example.com ', password: 'x' })).toEqual({
      ok: true,
      values: { email: 'camille@example.com', password: 'x' },
    });
  });

  it('exige un email valide', () => {
    expect(validateLogin({ email: 'pas-un-email', password: 'x' })).toEqual({
      ok: false,
      errors: { email: 'Saisissez une adresse email valide.' },
    });
  });

  it('exige un mot de passe', () => {
    expect(validateLogin({ email: GOOD.email, password: '' })).toEqual({
      ok: false,
      errors: { password: 'Saisissez votre mot de passe.' },
    });
  });

  it('refuse un mot de passe demesure sans l appeler', () => {
    const result = validateLogin({ email: GOOD.email, password: 'a'.repeat(129) });

    expect(result.ok).toBe(false);
  });
});

describe('submitLogin', () => {
  it('n appelle pas l API quand la saisie est invalide', async () => {
    const fetchImpl = vi.fn();

    const state = await submitLogin({ email: 'x', password: '' }, fetchImpl);

    expect(state.status).toBe('invalid');
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('garde le jeton d acces en memoire apres une connexion reussie', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(jsonResponse({ access_token: 'jeton', token_type: 'Bearer', expires_in: 900 }, 200));

    const state = await submitLogin(GOOD, fetchImpl);

    expect(state).toEqual({ status: 'success' });
    expect(getAccessToken()).toBe('jeton');
  });

  it('ne revele pas la cause d un refus et ne cree aucune session', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ detail: 'Identifiants invalides.' }, 401));

    const state = await submitLogin(GOOD, fetchImpl);

    expect(state).toEqual({ status: 'error', message: 'Email ou mot de passe incorrect.' });
    expect(getAccessToken()).toBeNull();
  });

  it('explique une limitation de debit', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('', { status: 429 }));

    const state = await submitLogin(GOOD, fetchImpl);

    expect(state).toEqual({
      status: 'error',
      message: 'Trop de tentatives. Patientez une minute avant de réessayer.',
    });
  });

  it.each([[jsonResponse({ detail: 'Requete invalide.' }, 422)], [new Response('', { status: 503 })]])(
    'affiche un message generique quand le service est indisponible ou refuse la saisie',
    async (response) => {
      const state = await submitLogin(GOOD, vi.fn().mockResolvedValue(response));

      expect(state.status).toBe('error');
      expect(JSON.stringify(state)).not.toContain(GOOD.password);
    }
  );

  it('remplace une session precedente par la nouvelle', async () => {
    const first = vi
      .fn()
      .mockResolvedValue(
        jsonResponse({ access_token: 'premier', token_type: 'Bearer', expires_in: 900 }, 200)
      );
    const second = vi
      .fn()
      .mockResolvedValue(
        jsonResponse({ access_token: 'second', token_type: 'Bearer', expires_in: 900 }, 200)
      );

    await submitLogin(GOOD, first);
    await submitLogin(GOOD, second);

    expect(getAccessToken()).toBe('second');
  });
});

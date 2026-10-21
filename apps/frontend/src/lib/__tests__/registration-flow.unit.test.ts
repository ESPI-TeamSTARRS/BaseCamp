import { describe, expect, it, vi } from 'vitest';
import {
  readVerificationToken,
  submitRegistration,
  validateRegistration,
  verifyFromHash,
} from '../registration-flow';

const GOOD = { email: 'camille@example.com', password: 'sentier-du-mont-blanc' };

describe('validateRegistration', () => {
  it('accepte un email valide et 12 caracteres, sans regle de composition', () => {
    expect(validateRegistration({ email: ' Camille@Example.com ', password: 'a'.repeat(12) })).toEqual({
      ok: true,
      values: { email: 'camille@example.com', password: 'a'.repeat(12) },
    });
  });

  it('refuse un email invalide avec un message en francais', () => {
    const result = validateRegistration({ email: 'pas-un-email', password: GOOD.password });

    expect(result).toEqual({ ok: false, errors: { email: 'Saisissez une adresse email valide.' } });
  });

  it('refuse un mot de passe de moins de 12 caracteres', () => {
    const result = validateRegistration({ email: GOOD.email, password: 'a'.repeat(11) });

    expect(result).toEqual({
      ok: false,
      errors: { password: 'Le mot de passe doit contenir au moins 12 caractères.' },
    });
  });

  it('refuse un mot de passe de plus de 128 caracteres', () => {
    const result = validateRegistration({ email: GOOD.email, password: 'a'.repeat(129) });

    expect(result).toEqual({
      ok: false,
      errors: { password: 'Le mot de passe ne doit pas dépasser 128 caractères.' },
    });
  });

  it('signale les deux champs a la fois', () => {
    const result = validateRegistration({ email: '', password: '' });

    expect(result.ok).toBe(false);
    expect(result.ok === false && Object.keys(result.errors)).toEqual(['email', 'password']);
  });
});

describe('submitRegistration', () => {
  it('n appelle pas l API quand la saisie est invalide', async () => {
    const fetchImpl = vi.fn();

    const state = await submitRegistration({ email: 'x', password: 'court' }, fetchImpl);

    expect(state.status).toBe('invalid');
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('rend l etat succes avec l adresse normalisee', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('{}', { status: 202 }));

    const state = await submitRegistration(
      { email: 'Camille@Example.com', password: GOOD.password },
      fetchImpl
    );

    expect(state).toEqual({ status: 'success', email: 'camille@example.com' });
  });

  it('affiche les messages du serveur (mot de passe courant)', async () => {
    const body = {
      fields: ['password'],
      messages: ['Ce mot de passe est trop courant, choisissez-en un autre.'],
    };
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 422 }));

    const state = await submitRegistration(GOOD, fetchImpl);

    expect(state).toEqual({
      status: 'invalid',
      errors: { password: 'Ce mot de passe est trop courant, choisissez-en un autre.' },
    });
  });

  it('retombe sur un message generique si le 422 n a pas de message', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ fields: ['email'] }), { status: 422 }));

    const state = await submitRegistration(GOOD, fetchImpl);

    expect(state).toEqual({ status: 'invalid', errors: { email: 'Cette saisie est invalide.' } });
  });

  it('rend un message sans detail technique pour le debit et l indisponibilite', async () => {
    const limited = await submitRegistration(
      GOOD,
      vi.fn().mockResolvedValue(new Response('', { status: 429 }))
    );
    const down = await submitRegistration(GOOD, vi.fn().mockRejectedValue(new Error('ECONNREFUSED stack')));

    expect(limited).toEqual({
      status: 'error',
      message: 'Trop de tentatives. Patientez une minute avant de réessayer.',
    });
    expect(down).toEqual({
      status: 'error',
      message: 'Le service est momentanément indisponible. Réessayez dans quelques instants.',
    });
  });
});

describe('readVerificationToken', () => {
  it('lit le jeton dans le fragment d URL', () => {
    expect(readVerificationToken('#token=abc_DEF-123')).toBe('abc_DEF-123');
  });

  it.each(['', '#', '#autre=1', '#token=', '#token=' + 'a'.repeat(300), '#token=a b', '#token=<x>'])(
    'rend null pour %j',
    (hash) => {
      expect(readVerificationToken(hash)).toBeNull();
    }
  );
});

describe('verifyFromHash', () => {
  it('rend missing sans appeler l API quand le lien n a pas de jeton', async () => {
    const fetchImpl = vi.fn();

    expect(await verifyFromHash('', fetchImpl)).toEqual({ status: 'missing' });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('rend verified quand le jeton est accepte', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));

    expect(await verifyFromHash('#token=abc123', fetchImpl)).toEqual({ status: 'verified' });
  });

  it('rend le meme etat invalide pour un jeton inconnu, expire ou utilise', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('{}', { status: 400 }));

    expect(await verifyFromHash('#token=abc123', fetchImpl)).toEqual({ status: 'invalid' });
  });

  it('rend unavailable quand le service ne repond pas', async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new Error('down'));

    expect(await verifyFromHash('#token=abc123', fetchImpl)).toEqual({ status: 'unavailable' });
  });
});

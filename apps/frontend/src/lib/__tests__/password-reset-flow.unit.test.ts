import { describe, expect, it, vi } from 'vitest';
import {
  readResetToken,
  submitForgotPassword,
  submitPasswordReset,
  validateNewPassword,
} from '../password-reset-flow';

const PASSWORD = 'sentier-du-mont-blanc';

describe('submitForgotPassword', () => {
  it('refuse une adresse invalide sans appeler l API', async () => {
    const fetchImpl = vi.fn();

    const state = await submitForgotPassword('pas-un-email', fetchImpl);

    expect(state).toEqual({ status: 'invalid', message: 'Saisissez une adresse email valide.' });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('rend le meme succes neutre avec l adresse normalisee', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('{}', { status: 202 }));

    const state = await submitForgotPassword(' Camille@Example.com ', fetchImpl);

    expect(state).toEqual({ status: 'success', email: 'camille@example.com' });
    expect(JSON.parse(fetchImpl.mock.calls[0][1].body)).toEqual({ email: 'camille@example.com' });
  });

  it('rend un message sans detail technique pour le debit et l indisponibilite', async () => {
    const limited = await submitForgotPassword(
      'a@b.co',
      vi.fn().mockResolvedValue(new Response('', { status: 429 }))
    );
    const down = await submitForgotPassword(
      'a@b.co',
      vi.fn().mockRejectedValue(new Error('ECONNREFUSED stack'))
    );

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

describe('readResetToken', () => {
  it('lit le jeton dans le fragment d URL', () => {
    expect(readResetToken('#token=abc_DEF-123')).toBe('abc_DEF-123');
  });

  it.each(['', '#', '#autre=1', '#token=', '#token=a b', '#token=' + 'a'.repeat(300)])(
    'rend null pour %j',
    (hash) => {
      expect(readResetToken(hash)).toBeNull();
    }
  );
});

describe('validateNewPassword', () => {
  it('accepte 12 caracteres sans regle de composition quand la confirmation correspond', () => {
    expect(validateNewPassword('a'.repeat(12), 'a'.repeat(12))).toEqual({ ok: true });
  });

  it('refuse moins de 12 et plus de 128 caracteres', () => {
    expect(validateNewPassword('a'.repeat(11), 'a'.repeat(11))).toEqual({
      ok: false,
      errors: { password: 'Le mot de passe doit contenir au moins 12 caractères.' },
    });
    expect(validateNewPassword('a'.repeat(129), 'a'.repeat(129))).toEqual({
      ok: false,
      errors: { password: 'Le mot de passe ne doit pas dépasser 128 caractères.' },
    });
  });

  it('refuse une confirmation differente', () => {
    expect(validateNewPassword(PASSWORD, PASSWORD + 'x')).toEqual({
      ok: false,
      errors: { confirmation: 'Les deux mots de passe ne correspondent pas.' },
    });
  });
});

describe('submitPasswordReset', () => {
  it('rend missing sans appeler l API quand le lien n a pas de jeton', async () => {
    const fetchImpl = vi.fn();

    const state = await submitPasswordReset(
      { hash: '', password: PASSWORD, confirmation: PASSWORD },
      fetchImpl
    );

    expect(state).toEqual({ status: 'missing' });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('n appelle pas l API quand la saisie est invalide', async () => {
    const fetchImpl = vi.fn();

    const state = await submitPasswordReset(
      { hash: '#token=abc', password: 'court', confirmation: 'court' },
      fetchImpl
    );

    expect(state.status).toBe('invalid');
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('rend success quand le mot de passe est remplace', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));

    const state = await submitPasswordReset(
      { hash: '#token=abc', password: PASSWORD, confirmation: PASSWORD },
      fetchImpl
    );

    expect(state).toEqual({ status: 'success' });
    expect(JSON.parse(fetchImpl.mock.calls[0][1].body)).toEqual({ token: 'abc', password: PASSWORD });
  });

  it('rend le meme etat pour un lien inconnu, expire ou deja utilise', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('{}', { status: 400 }));

    const state = await submitPasswordReset(
      { hash: '#token=abc', password: PASSWORD, confirmation: PASSWORD },
      fetchImpl
    );

    expect(state).toEqual({ status: 'invalid_token' });
  });

  it('affiche le refus serveur d un mot de passe courant sur le champ', async () => {
    const body = {
      fields: ['password'],
      messages: ['Ce mot de passe est trop courant, choisissez-en un autre.'],
    };
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 422 }));

    const state = await submitPasswordReset(
      { hash: '#token=abc', password: 'Password1234', confirmation: 'Password1234' },
      fetchImpl
    );

    expect(state).toEqual({
      status: 'invalid',
      errors: { password: 'Ce mot de passe est trop courant, choisissez-en un autre.' },
    });
  });

  it('rend un message sans detail technique pour le debit et l indisponibilite', async () => {
    const input = { hash: '#token=abc', password: PASSWORD, confirmation: PASSWORD };

    const limited = await submitPasswordReset(
      input,
      vi.fn().mockResolvedValue(new Response('', { status: 429 }))
    );
    const down = await submitPasswordReset(input, vi.fn().mockRejectedValue(new Error('stack')));

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

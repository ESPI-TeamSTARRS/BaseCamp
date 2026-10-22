import { describe, expect, it } from 'vitest';
import {
  EMPTY_LOCKOUT,
  LOCK_DURATION_MS,
  isLocked,
  parseLockout,
  recordFailure,
  recordSuccess,
  remainingMs,
} from '../lockout';

const T0 = 1_000_000;

describe('blocage local de la connexion', () => {
  it('ne bloque pas avant le seuil de mots de passe faux', () => {
    let state = EMPTY_LOCKOUT;
    state = recordFailure(state, 'password', T0);
    state = recordFailure(state, 'password', T0 + 1000);
    expect(isLocked(state, T0 + 2000)).toBe(false);
  });

  it('bloque 5 minutes après 3 mots de passe faux', () => {
    let state = EMPTY_LOCKOUT;
    for (let i = 0; i < 3; i++) state = recordFailure(state, 'password', T0 + i);
    expect(isLocked(state, T0 + 10)).toBe(true);
    expect(remainingMs(state, T0 + 2)).toBe(LOCK_DURATION_MS);
    expect(isLocked(state, T0 + 2 + LOCK_DURATION_MS)).toBe(false);
  });

  it('bloque 5 minutes après 5 visages refusés, pas avant', () => {
    let state = EMPTY_LOCKOUT;
    for (let i = 0; i < 4; i++) state = recordFailure(state, 'face', T0 + i);
    expect(isLocked(state, T0 + 10)).toBe(false);
    state = recordFailure(state, 'face', T0 + 5);
    expect(isLocked(state, T0 + 10)).toBe(true);
  });

  it('tient des compteurs séparés pour le visage et le mot de passe', () => {
    let state = EMPTY_LOCKOUT;
    for (let i = 0; i < 4; i++) state = recordFailure(state, 'face', T0 + i);
    for (let i = 0; i < 2; i++) state = recordFailure(state, 'password', T0 + i);
    expect(isLocked(state, T0 + 10)).toBe(false);
  });

  it('oublie les échecs plus anciens que la fenêtre de 10 minutes', () => {
    let state = recordFailure(EMPTY_LOCKOUT, 'password', T0);
    state = recordFailure(state, 'password', T0 + 1000);
    state = recordFailure(state, 'password', T0 + 11 * 60_000);
    expect(isLocked(state, T0 + 11 * 60_000)).toBe(false);
  });

  it('un succès remet les compteurs à zéro', () => {
    let state = recordFailure(EMPTY_LOCKOUT, 'password', T0);
    state = recordSuccess(state);
    expect(state).toEqual(EMPTY_LOCKOUT);
  });

  it('un échec pendant le blocage ne le prolonge pas', () => {
    let state = EMPTY_LOCKOUT;
    for (let i = 0; i < 3; i++) state = recordFailure(state, 'password', T0);
    const again = recordFailure(state, 'password', T0 + 1000);
    expect(again.lockedUntil).toBe(state.lockedUntil);
  });

  it('remainingMs vaut 0 hors blocage', () => {
    expect(remainingMs(EMPTY_LOCKOUT, T0)).toBe(0);
  });

  it('parseLockout relit un état valide et rejette le reste', () => {
    const valid = { face: 1, password: 2, windowStart: 5, lockedUntil: 9 };
    expect(parseLockout(JSON.stringify(valid))).toEqual(valid);
    expect(parseLockout(null)).toEqual(EMPTY_LOCKOUT);
    expect(parseLockout('pas du json')).toEqual(EMPTY_LOCKOUT);
    expect(parseLockout('{"face":"x"}')).toEqual(EMPTY_LOCKOUT);
  });
});

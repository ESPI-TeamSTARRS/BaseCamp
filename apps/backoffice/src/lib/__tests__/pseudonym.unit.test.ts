import { describe, expect, it } from 'vitest';
import { pseudonymize } from '../pseudonym';

describe('pseudonymize', () => {
  it('donne une empreinte stable de 16 caractères, insensible à la casse et aux espaces', () => {
    const one = pseudonymize('Camille.Martin@Example.org ', 'cle-de-test');
    expect(one).toMatch(/^[0-9a-f]{16}$/);
    expect(pseudonymize('camille.martin@example.org', 'cle-de-test')).toBe(one);
  });

  it("change avec la clé et ne contient jamais l'adresse", () => {
    const one = pseudonymize('a@b.c', 'cle-1');
    expect(pseudonymize('a@b.c', 'cle-2')).not.toBe(one);
    expect(one).not.toContain('a@b.c');
  });
});

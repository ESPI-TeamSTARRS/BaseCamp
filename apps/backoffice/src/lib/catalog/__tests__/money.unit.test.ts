import { describe, expect, it } from 'vitest';
import { centsToInput, formatEuros, parseEuros } from '../money';

describe('parseEuros', () => {
  it.each([
    ['12', 1200],
    ['12,5', 1250],
    ['12.50', 1250],
    ['0', 0],
    ['0,05', 5],
    [' 99,99 ', 9999],
    ['100000', 10_000_000],
  ])('lit « %s » comme %i centimes', (text, cents) => {
    expect(parseEuros(text)).toBe(cents);
  });

  it.each(['', 'abc', '-3', '1,234', '12,', ',5', '100000,01', '1 000', '1e3', '12 €'])(
    'refuse « %s »',
    (text) => {
      expect(parseEuros(text)).toBeNull();
    }
  );
});

describe('affichage des prix', () => {
  it('rend les centimes en saisie', () => {
    expect(centsToInput(1250)).toBe('12,50');
    expect(centsToInput(1200)).toBe('12');
    expect(centsToInput(5)).toBe('0,05');
    expect(centsToInput(null)).toBe('');
  });

  it('formate en euros à la française', () => {
    expect(formatEuros(129900).replace(/\s/g, ' ')).toBe('1 299,00 €');
  });
});

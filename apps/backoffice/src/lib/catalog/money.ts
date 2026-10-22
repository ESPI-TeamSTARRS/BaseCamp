// Prix : l'API ne connait que des centimes entiers ; la saisie est en euros, virgule ou point.

const MAX_CENTS = 10_000_000;

/** « 12,5 » -> 1250 ; null si ce n'est pas un montant valide (negatif, plus de deux decimales, trop grand). */
export function parseEuros(text: string): number | null {
  const match = /^(\d{1,6})(?:[.,](\d{1,2}))?$/.exec(text.trim());
  if (!match) return null;
  const cents = Number(match[1]) * 100 + Number((match[2] ?? '').padEnd(2, '0'));
  return cents <= MAX_CENTS ? cents : null;
}

export function centsToInput(cents: number | null): string {
  if (cents === null) return '';
  const euros = Math.floor(cents / 100);
  const rest = cents % 100;
  return rest === 0 ? String(euros) : `${euros},${String(rest).padStart(2, '0')}`;
}

export function formatEuros(cents: number): string {
  return new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' }).format(cents / 100);
}

import { createHmac } from 'node:crypto';

const LENGTH = 16;

/** Empreinte HMAC-SHA256 tronquee d'une adresse : correlable dans les journaux, jamais reversible. */
export function pseudonymize(value: string, key: string): string {
  return createHmac('sha256', key).update(value.trim().toLowerCase()).digest('hex').slice(0, LENGTH);
}

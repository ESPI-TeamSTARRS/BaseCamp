import { lookupOrder, type LookupResult, type TrackedOrder } from './order-lookup';

const STORAGE_KEY = 'basecamp:last-order';

export type RecapResult =
  { kind: 'recap'; order: TrackedOrder } | { kind: 'no_email' } | { kind: 'unavailable' };

/**
 * Mémorise le dernier numéro et son email dans le stockage de l'onglet (effacé à sa fermeture) :
 * c'est ce qui permet de relire la commande à l'arrivée sur la page de succès, sans jamais mettre
 * l'email dans une URL. Un stockage refusé ne casse rien.
 */
export function rememberLastOrder(storage: Storage | undefined, number: string, email: string): void {
  try {
    storage?.setItem(STORAGE_KEY, JSON.stringify({ number, email }));
  } catch {
    // Stockage indisponible : la page de succès proposera la recherche manuelle.
  }
}

function emailFor(storage: Storage | undefined, number: string): string | null {
  try {
    const raw = storage?.getItem(STORAGE_KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw) as { number?: unknown; email?: unknown };
    return saved.number === number && typeof saved.email === 'string' ? saved.email : null;
  } catch {
    return null;
  }
}

/** Relit la commande côté serveur (récapitulatif réel). Ne rejette jamais. */
export async function loadRecap(
  number: string,
  storage: Storage | undefined,
  lookup: (number: string, email: string) => Promise<LookupResult> = lookupOrder
): Promise<RecapResult> {
  const email = emailFor(storage, number);
  if (email === null) return { kind: 'no_email' };
  try {
    const result = await lookup(number, email);
    if (result.ok) return { kind: 'recap', order: result.order };
    return result.reason === 'unavailable' ? { kind: 'unavailable' } : { kind: 'no_email' };
  } catch {
    return { kind: 'unavailable' };
  }
}

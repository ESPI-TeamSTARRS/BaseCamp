import { createPublicKey, type KeyObject } from 'node:crypto';

type FetchLike = typeof fetch;

const TIMEOUT_MS = 3000;

/** Cles publiques d'`auth` (JWKS), gardees 5 minutes; une cle inconnue relance une lecture au plus toutes les 10 s. */
export class JwksCache {
  private keys = new Map<string, KeyObject>();
  private fetchedAt = Number.NEGATIVE_INFINITY;
  private attemptedAt = Number.NEGATIVE_INFINITY;

  constructor(
    private readonly url: string,
    private readonly fetchImpl: FetchLike,
    private readonly nowMs: () => number,
    private readonly ttlMs: number,
    private readonly minRefetchMs: number
  ) {}

  /** La cle de ce `kid`, ou null si `auth` ne la publie pas. Leve `jwks_unavailable` sans aucune cle lisible. */
  async keyFor(kid: string): Promise<KeyObject | null> {
    const now = this.nowMs();
    const fresh = now - this.fetchedAt < this.ttlMs;
    const known = this.keys.get(kid);
    if (known && fresh) return known;
    if (now - this.attemptedAt >= this.minRefetchMs || (!known && this.keys.size === 0)) {
      await this.refresh(now);
    }
    return this.keys.get(kid) ?? null;
  }

  private async refresh(now: number): Promise<void> {
    this.attemptedAt = now;
    try {
      const response = await this.fetchImpl(this.url, {
        cache: 'no-store',
        signal: AbortSignal.timeout(TIMEOUT_MS),
      });
      if (!response.ok) throw new Error('status');
      const document = (await response.json()) as { keys?: unknown };
      this.keys = this.parse(document.keys);
      this.fetchedAt = now;
    } catch {
      if (this.keys.size === 0) throw new Error('jwks_unavailable');
    }
  }

  private parse(entries: unknown): Map<string, KeyObject> {
    const parsed = new Map<string, KeyObject>();
    if (!Array.isArray(entries)) return parsed;
    for (const entry of entries as Record<string, unknown>[]) {
      if (entry.kty !== 'OKP' || entry.crv !== 'Ed25519' || typeof entry.kid !== 'string') continue;
      try {
        parsed.set(entry.kid, createPublicKey({ key: entry as never, format: 'jwk' }));
      } catch {
        // cle illisible : ignoree
      }
    }
    return parsed;
  }
}

// Limiteur sliding-window en mémoire pour les routes publiques sensibles (checkout, contact).
// Pour un déploiement multi-instance, remplacer par un store partagé (Redis/Upstash).

const WINDOW_MS = 60_000;
const buckets = new Map<string, number[]>();

export function rateLimit(key: string, maxRequests: number): { allowed: boolean; retryAfterSeconds: number } {
  const now = Date.now();
  const timestamps = (buckets.get(key) ?? []).filter((t) => now - t < WINDOW_MS);

  if (timestamps.length >= maxRequests) {
    const oldestInWindow = timestamps[0];
    const retryAfterSeconds = Math.ceil((WINDOW_MS - (now - oldestInWindow)) / 1000);
    return { allowed: false, retryAfterSeconds };
  }

  timestamps.push(now);
  buckets.set(key, timestamps);
  return { allowed: true, retryAfterSeconds: 0 };
}

// ATTENTION : X-Forwarded-For n'est fiable que si l'application est déployée derrière un reverse-proxy
// de confiance (Traefik/Cloudflare, voir .claude/skills/sec-infra-hardening) qui écrase tout en-tête
// falsifié par le client avant de fixer le sien. En exposition directe, un attaquant peut usurper cet
// en-tête et contourner la limite par IP — ne jamais déployer cette route sans proxy de confiance en amont.
export function getClientIp(req: Request): string {
  const forwarded = req.headers.get('x-forwarded-for');
  return forwarded?.split(',')[0]?.trim() ?? 'unknown';
}

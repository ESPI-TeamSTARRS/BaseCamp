// Origine d'une requete : anti-CSRF des formulaires et reconstruction des URLs publiques derriere Traefik.

const HOST_RE = /^[A-Za-z0-9.-]+(:\d{1,5})?$/;

/** Un POST doit venir de la page du back-office elle-meme (en plus de SameSite=Strict sur les cookies). */
export function isSameOrigin(request: Request): boolean {
  const site = request.headers.get('sec-fetch-site');
  if (site === 'same-origin') return true;
  const origin = request.headers.get('origin');
  const host = request.headers.get('host');
  if (!origin || !host) return false;
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

/** URL publique (hote et schema vus par le navigateur) : jamais l'adresse interne du conteneur. */
export function publicUrl(request: Request, path: string): URL {
  const forwardedHost = request.headers.get('x-forwarded-host');
  const host =
    forwardedHost && HOST_RE.test(forwardedHost)
      ? forwardedHost
      : (request.headers.get('host') ?? 'localhost');
  const forwardedProto = request.headers.get('x-forwarded-proto');
  const proto = forwardedProto === 'https' ? 'https' : 'http';
  return new URL(path, `${proto}://${HOST_RE.test(host) ? host : 'localhost'}`);
}

export function isSecure(request: Request): boolean {
  return request.headers.get('x-forwarded-proto') === 'https';
}

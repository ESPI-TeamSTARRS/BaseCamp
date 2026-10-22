import { randomBytes } from 'node:crypto';
import { AuthBackofficeClient } from './auth-backoffice-client';
import { JwksCache } from './jwks-cache';
import { SessionService } from './session-service';
import { TokenVerifier } from './token-verifier';

// Assemblage des dependances a partir de l'environnement du conteneur (reseau interne `app`).
// La cle de pseudonymisation vient de l'environnement ; sans elle (developpement), une cle ephemere
// est tiree : les empreintes changent a chaque demarrage.

const DEFAULT_AUTH_URL = 'http://auth:8000';
const JWKS_TTL_MS = 300_000;
const JWKS_MIN_REFETCH_MS = 10_000;

interface Runtime {
  sessions: SessionService;
  client: AuthBackofficeClient;
  pseudonymKey: string;
}

let cached: Runtime | undefined;

export function runtime(env: Record<string, string | undefined> = process.env): Runtime {
  if (cached === undefined) {
    const authUrl = env.AUTH_URL || DEFAULT_AUTH_URL;
    const jwks = new JwksCache(
      `${authUrl}/.well-known/jwks.json`,
      fetch,
      Date.now,
      JWKS_TTL_MS,
      JWKS_MIN_REFETCH_MS
    );
    const verifier = new TokenVerifier(
      jwks,
      env.AUTH_ISSUER || 'basecamp-auth',
      env.AUTH_AUDIENCE || 'basecamp-client-api'
    );
    cached = {
      sessions: new SessionService(verifier),
      client: new AuthBackofficeClient(authUrl),
      pseudonymKey: env.LOG_PSEUDONYM_KEY || randomBytes(16).toString('hex'),
    };
  }
  return cached;
}

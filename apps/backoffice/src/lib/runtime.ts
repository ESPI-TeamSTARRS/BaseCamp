import { randomBytes } from 'node:crypto';
import { AuthBackofficeClient } from './auth-backoffice-client';
import { JwksCache } from './jwks-cache';
import { SessionService } from './session-service';
import { ShopClient } from './shop-client';
import { TokenVerifier } from './token-verifier';

// Assemblage des dependances a partir de l'environnement du conteneur (reseau interne `app`).
// Les adresses internes des services (AUTH_URL, SHOP_URL) viennent toujours de l'environnement (compose) :
// aucune adresse n'est ecrite en dur, et un oubli est une erreur claire plutot qu'un appel perdu.
// La cle de pseudonymisation vient aussi de l'environnement ; sans elle (developpement), une cle ephemere
// est tiree : les empreintes changent a chaque demarrage.

const JWKS_TTL_MS = 300_000;
const JWKS_MIN_REFETCH_MS = 10_000;

interface Runtime {
  sessions: SessionService;
  client: AuthBackofficeClient;
  shop: ShopClient;
  pseudonymKey: string;
}

type Env = Record<string, string | undefined>;

function required(env: Env, name: string): string {
  const value = env[name];
  if (!value) throw new Error(`${name} est obligatoire (voir docker-compose.yml)`);
  return value;
}

export function buildRuntime(env: Env): Runtime {
  const authUrl = required(env, 'AUTH_URL');
  const shopUrl = required(env, 'SHOP_URL');
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
  return {
    sessions: new SessionService(verifier),
    client: new AuthBackofficeClient(authUrl),
    shop: new ShopClient(shopUrl),
    pseudonymKey: env.LOG_PSEUDONYM_KEY || randomBytes(16).toString('hex'),
  };
}

let cached: Runtime | undefined;

export function runtime(env: Env = process.env): Runtime {
  cached ??= buildRuntime(env);
  return cached;
}

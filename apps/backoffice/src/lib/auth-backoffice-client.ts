// Appels du back-office aux trois temps de la connexion d'`auth` (/backoffice/*), sur le reseau interne.
// Aucun mot de passe, aucune image ni aucun jeton n'est jamais reflete dans une erreur.

export interface StepContext {
  correlationId: string;
  forwardedFor?: string;
}

export type IdentifyResult = { kind: 'ok'; challengeId: string; expiresIn: number } | { kind: 'unavailable' };
export type FaceResult =
  { kind: 'ok' } | { kind: 'refused' } | { kind: 'invalid_images' } | { kind: 'unavailable' };
export type PasswordResult =
  { kind: 'ok'; accessToken: string; expiresIn: number } | { kind: 'refused' } | { kind: 'unavailable' };

type FetchLike = typeof fetch;

const TIMEOUT_MS = 8000;

export class AuthBackofficeClient {
  constructor(
    private readonly baseUrl: string,
    private readonly fetchImpl: FetchLike = fetch
  ) {}

  async identify(email: string, context: StepContext): Promise<IdentifyResult> {
    const reply = await this.post('/backoffice/identify', { email }, context);
    const body = reply?.status === 200 ? await readJson(reply) : null;
    if (typeof body?.challenge_id !== 'string' || typeof body.expires_in !== 'number')
      return { kind: 'unavailable' };
    return { kind: 'ok', challengeId: body.challenge_id, expiresIn: body.expires_in };
  }

  async face(challengeId: string, images: string[], context: StepContext): Promise<FaceResult> {
    const reply = await this.post('/backoffice/face', { challenge_id: challengeId, images }, context);
    if (reply === null) return { kind: 'unavailable' };
    if (reply.status === 401) return { kind: 'refused' };
    if (reply.status === 422) return { kind: 'invalid_images' };
    const body = reply.status === 200 ? await readJson(reply) : null;
    return body?.face_ok === true ? { kind: 'ok' } : { kind: 'unavailable' };
  }

  async password(challengeId: string, password: string, context: StepContext): Promise<PasswordResult> {
    const reply = await this.post('/backoffice/password', { challenge_id: challengeId, password }, context);
    if (reply === null) return { kind: 'unavailable' };
    if (reply.status === 401) return { kind: 'refused' };
    const body = reply.status === 200 ? await readJson(reply) : null;
    if (typeof body?.access_token !== 'string' || typeof body.expires_in !== 'number')
      return { kind: 'unavailable' };
    return { kind: 'ok', accessToken: body.access_token, expiresIn: body.expires_in };
  }

  private async post(path: string, body: unknown, context: StepContext): Promise<Response | null> {
    const headers = new Headers({
      'content-type': 'application/json',
      'x-correlation-id': context.correlationId,
    });
    if (context.forwardedFor) headers.set('x-forwarded-for', context.forwardedFor);
    try {
      return await this.fetchImpl(`${this.baseUrl}${path}`, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
        redirect: 'error',
        cache: 'no-store',
        signal: AbortSignal.timeout(TIMEOUT_MS),
      });
    } catch {
      return null;
    }
  }
}

async function readJson(response: Response): Promise<Record<string, unknown> | null> {
  try {
    const value: unknown = await response.json();
    return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

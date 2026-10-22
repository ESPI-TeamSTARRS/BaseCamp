import { NextResponse } from 'next/server';
import type { AuthBackofficeClient, StepContext } from '../auth-backoffice-client';
import { buildLogEvent, emit, resolveCorrelationId, type LogEvent, type Outcome } from '../log-event';
import { pseudonymize } from '../pseudonym';
import { isSameOrigin, isSecure } from '../request-origin';
import { setSession } from '../session-response';

// Les trois temps de la connexion (identification, visage, mot de passe) relayes vers `auth`.
// Le jeton d'acces n'est jamais renvoye au navigateur : a la derniere etape, il devient un cookie HttpOnly.

export interface StepDeps {
  client: Pick<AuthBackofficeClient, 'identify' | 'face' | 'password'>;
  pseudonymKey: string;
  log?: (event: LogEvent) => void;
}

const MAX_SMALL_BODY = 8192;
const MAX_FACE_BODY = 5 * 1024 * 1024;
const MAX_EMAIL = 254;
const MAX_PASSWORD = 256;
const MAX_IMAGES = 3;
const MAX_IMAGE_CHARS = 1_400_000; // 1 Mio en base64
const CHALLENGE_RE = /^[A-Za-z0-9_-]{16,128}$/;
const BASE64_RE = /^[A-Za-z0-9+/]+={0,2}$/;

const GENERIC_DENIAL = 'Identifiants invalides.';
const UNAVAILABLE = 'Service momentanément indisponible.';
const INVALID = 'Requete invalide.';

const reply = (status: number, detail: string) => NextResponse.json({ detail }, { status });

interface Prepared {
  body: Record<string, unknown>;
  context: StepContext;
  correlationId: string;
  record: (outcome: Outcome, reason?: string, attributes?: LogEvent['attributes']) => void;
}

/** Controles communs : origine, taille, JSON objet. Renvoie la reponse d'erreur ou les elements prets. */
async function prepare(
  request: Request,
  deps: StepDeps,
  event: string,
  maxBytes: number
): Promise<NextResponse | Prepared> {
  const log = deps.log ?? ((entry: LogEvent) => emit(entry));
  const correlationId = resolveCorrelationId(request.headers.get('x-correlation-id'), () =>
    crypto.randomUUID()
  );
  const record: Prepared['record'] = (outcome, reason, attributes) =>
    log(buildLogEvent({ event, correlationId, outcome, reason, attributes }));
  if (!isSameOrigin(request)) {
    record('denied', 'cross_origin');
    return new NextResponse('Requête refusée.', { status: 403 });
  }
  if (Number(request.headers.get('content-length') ?? '0') > maxBytes) {
    record('denied', 'body_too_large');
    return new NextResponse('Requête trop volumineuse.', { status: 413 });
  }
  const body: unknown = await request.json().catch(() => null);
  if (typeof body !== 'object' || body === null || Array.isArray(body)) {
    record('denied', 'invalid_form');
    return reply(422, INVALID);
  }
  const forwardedFor = request.headers.get('x-forwarded-for') ?? undefined;
  return {
    body: body as Record<string, unknown>,
    context: { correlationId, forwardedFor },
    correlationId,
    record,
  };
}

const isPrepared = (value: NextResponse | Prepared): value is Prepared => !(value instanceof NextResponse);

export async function handleIdentify(request: Request, deps: StepDeps): Promise<NextResponse> {
  const prepared = await prepare(request, deps, 'backoffice.login_identify', MAX_SMALL_BODY);
  if (!isPrepared(prepared)) return prepared;
  const { email } = prepared.body;
  if (typeof email !== 'string' || !email.includes('@') || email.length > MAX_EMAIL) {
    prepared.record('denied', 'invalid_form');
    return reply(422, INVALID);
  }
  const attributes = { email_hash: pseudonymize(email, deps.pseudonymKey) };
  const result = await deps.client.identify(email.trim(), prepared.context);
  if (result.kind === 'unavailable') {
    prepared.record('error', 'auth_unavailable', attributes);
    return reply(503, UNAVAILABLE);
  }
  prepared.record('success', undefined, attributes);
  return NextResponse.json({ challenge_id: result.challengeId, expires_in: result.expiresIn });
}

export async function handleFace(request: Request, deps: StepDeps): Promise<NextResponse> {
  const prepared = await prepare(request, deps, 'backoffice.login_face', MAX_FACE_BODY);
  if (!isPrepared(prepared)) return prepared;
  const { challenge_id: challengeId, images } = prepared.body;
  if (
    typeof challengeId !== 'string' ||
    !CHALLENGE_RE.test(challengeId) ||
    !Array.isArray(images) ||
    images.length < 1 ||
    images.length > MAX_IMAGES ||
    !images.every(
      (image) => typeof image === 'string' && image.length <= MAX_IMAGE_CHARS && BASE64_RE.test(image)
    )
  ) {
    prepared.record('denied', 'invalid_form');
    return reply(422, INVALID);
  }
  const result = await deps.client.face(challengeId, images as string[], prepared.context);
  if (result.kind === 'ok') {
    prepared.record('success');
    return NextResponse.json({ face_ok: true });
  }
  if (result.kind === 'refused') {
    prepared.record('denied', 'face_refused');
    return reply(401, GENERIC_DENIAL);
  }
  if (result.kind === 'invalid_images') {
    prepared.record('denied', 'invalid_images');
    return reply(422, 'Image invalide.');
  }
  prepared.record('error', 'auth_unavailable');
  return reply(503, UNAVAILABLE);
}

export async function handlePassword(request: Request, deps: StepDeps): Promise<NextResponse> {
  const prepared = await prepare(request, deps, 'backoffice.login_password', MAX_SMALL_BODY);
  if (!isPrepared(prepared)) return prepared;
  const { challenge_id: challengeId, password } = prepared.body;
  if (
    typeof challengeId !== 'string' ||
    !CHALLENGE_RE.test(challengeId) ||
    typeof password !== 'string' ||
    password.length === 0 ||
    password.length > MAX_PASSWORD
  ) {
    prepared.record('denied', 'invalid_form');
    return reply(422, INVALID);
  }
  const result = await deps.client.password(challengeId, password, prepared.context);
  if (result.kind === 'refused') {
    prepared.record('denied', 'wrong_password');
    return reply(401, GENERIC_DENIAL);
  }
  if (result.kind === 'unavailable') {
    prepared.record('error', 'auth_unavailable');
    return reply(503, UNAVAILABLE);
  }
  prepared.record('success');
  return setSession(NextResponse.json({ ok: true }), result.accessToken, result.expiresIn, isSecure(request));
}

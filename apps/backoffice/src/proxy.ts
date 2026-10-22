import { NextRequest, NextResponse } from 'next/server';
import { buildLogEvent, emit, resolveCorrelationId, type LogEvent } from '@/lib/log-event';
import { isSecure, publicUrl } from '@/lib/request-origin';
import { runtime } from '@/lib/runtime';
import { ACCESS_COOKIE } from '@/lib/session-cookies';
import { clearSession } from '@/lib/session-response';
import type { SessionService } from '@/lib/session-service';

export interface ProxyDeps {
  sessions: Pick<SessionService, 'evaluate'>;
  log?: (event: LogEvent) => void;
}

// Pages et actions accessibles sans session : la connexion elle-meme (trois temps), l'inscription par invitation (le jeton du lien en est la preuve) et robots.txt.
const PUBLIC_PATHS = new Set([
  '/login',
  '/invitation',
  '/session/identify',
  '/session/face',
  '/session/password',
  '/session/logout',
  '/robots.txt',
]);
const API_PREFIX = '/bff/';

/** Garde de route + une ligne de journal par page (contrat commun) + X-Correlation-ID propage. */
export function createProxy(deps: ProxyDeps) {
  const log = deps.log ?? ((event: LogEvent) => emit(event));
  return async function proxy(request: NextRequest): Promise<NextResponse> {
    const correlationId = resolveCorrelationId(request.headers.get('x-correlation-id'), () =>
      crypto.randomUUID()
    );
    const path = request.nextUrl.pathname;
    const finish = (response: NextResponse) => {
      response.headers.set('X-Correlation-ID', correlationId);
      return response;
    };
    const served = () =>
      log(buildLogEvent({ event: 'backoffice.page_served', correlationId, outcome: 'success' }));

    if (PUBLIC_PATHS.has(path)) {
      served();
      return finish(NextResponse.next());
    }
    const result = await deps.sessions.evaluate(request.cookies.get(ACCESS_COOKIE)?.value);
    if (result.kind === 'valid') {
      served();
      return finish(NextResponse.next());
    }
    if (result.kind === 'error') {
      log(
        buildLogEvent({
          event: 'backoffice.access_denied',
          correlationId,
          outcome: 'error',
          reason: result.reason,
        })
      );
      return finish(NextResponse.redirect(publicUrl(request, '/login?erreur=2')));
    }
    log(
      buildLogEvent({
        event: 'backoffice.access_denied',
        correlationId,
        outcome: 'denied',
        reason: result.reason,
      })
    );
    const secure = isSecure(request);
    if (path.startsWith(API_PREFIX)) {
      return finish(
        clearSession(NextResponse.json({ detail: 'Authentification requise.' }, { status: 401 }), secure)
      );
    }
    return finish(clearSession(NextResponse.redirect(publicUrl(request, '/login')), secure));
  };
}

export async function proxy(request: NextRequest): Promise<NextResponse> {
  return createProxy({ sessions: runtime().sessions })(request);
}

export const config = { matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'] };

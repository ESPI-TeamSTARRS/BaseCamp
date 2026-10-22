import { NextResponse } from 'next/server';
import { buildLogEvent, emit, resolveCorrelationId, type LogEvent } from '../log-event';
import { isSameOrigin, isSecure, publicUrl } from '../request-origin';
import { clearSession } from '../session-response';

export interface LogoutDeps {
  log?: (event: LogEvent) => void;
}

/** Deconnexion : efface le cookie de session (le jeton du back-office n'a pas de session a revoquer chez auth). */
export function handleLogout(request: Request, deps: LogoutDeps = {}): NextResponse {
  const log = deps.log ?? ((event: LogEvent) => emit(event));
  const correlationId = resolveCorrelationId(request.headers.get('x-correlation-id'), () =>
    crypto.randomUUID()
  );
  if (!isSameOrigin(request)) {
    log(
      buildLogEvent({ event: 'backoffice.logout', correlationId, outcome: 'denied', reason: 'cross_origin' })
    );
    return new NextResponse('Requête refusée.', { status: 403 });
  }
  log(buildLogEvent({ event: 'backoffice.logout', correlationId, outcome: 'success' }));
  return clearSession(NextResponse.redirect(publicUrl(request, '/login'), 303), isSecure(request));
}

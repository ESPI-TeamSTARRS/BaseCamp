import { NextRequest, NextResponse } from 'next/server';
import { buildLogEvent, emit, resolveCorrelationId } from '@/lib/log-event';

// Une ligne de journal par page servie (contrat commun) et un X-Correlation-ID propage.
export function proxy(request: NextRequest): NextResponse {
  const correlationId = resolveCorrelationId(request.headers.get('x-correlation-id'), () =>
    crypto.randomUUID()
  );
  emit(buildLogEvent({ event: 'backoffice.page_served', correlationId, outcome: 'success' }));
  const response = NextResponse.next();
  response.headers.set('X-Correlation-ID', correlationId);
  return response;
}

export const config = { matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'] };

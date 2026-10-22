import { describe, expect, it } from 'vitest';
import { handleLogout } from '../handlers/logout-handler';
import type { LogEvent } from '../log-event';

function post(headers: Record<string, string> = {}): Request {
  return new Request('http://backoffice:3000/session/logout', {
    method: 'POST',
    headers: {
      host: 'admin.localhost',
      'sec-fetch-site': 'same-origin',
      cookie: 'bo_access=a.b.c',
      ...headers,
    },
  });
}

describe('handleLogout', () => {
  it('efface le cookie de session et renvoie à la connexion', () => {
    const events: LogEvent[] = [];

    const response = handleLogout(post({ 'x-correlation-id': 'corr-12345678' }), {
      log: (event) => events.push(event),
    });

    expect(response.status).toBe(303);
    expect(response.headers.get('location')).toBe('http://admin.localhost/login');
    expect(response.headers.getSetCookie().join('\n')).toMatch(/bo_access=;.*Max-Age=0/i);
    expect(events[0]).toMatchObject({
      event: 'backoffice.logout',
      outcome: 'success',
      correlation_id: 'corr-12345678',
    });
  });

  it('refuse une requête venue d’un autre site, sans effacer quoi que ce soit', () => {
    const response = handleLogout(post({ 'sec-fetch-site': 'cross-site' }), { log: () => undefined });

    expect(response.status).toBe(403);
    expect(response.headers.getSetCookie()).toEqual([]);
  });
});

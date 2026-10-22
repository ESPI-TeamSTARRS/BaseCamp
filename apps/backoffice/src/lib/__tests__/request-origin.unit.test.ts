import { describe, expect, it } from 'vitest';
import { isSameOrigin, publicUrl } from '../request-origin';

const request = (headers: Record<string, string>, url = 'http://backoffice:3000/session/login') =>
  new Request(url, { method: 'POST', headers });

describe('isSameOrigin', () => {
  it('accepte Sec-Fetch-Site same-origin', () => {
    expect(isSameOrigin(request({ 'sec-fetch-site': 'same-origin', host: 'mercure.localhost' }))).toBe(true);
  });

  it("accepte une origine annoncée égale à l'hôte demandé", () => {
    expect(
      isSameOrigin(request({ origin: 'http://mercure.localhost:8265', host: 'mercure.localhost:8265' }))
    ).toBe(true);
  });

  it('refuse un autre site, une origine différente ou rien du tout', () => {
    expect(isSameOrigin(request({ 'sec-fetch-site': 'cross-site', host: 'mercure.localhost' }))).toBe(false);
    expect(isSameOrigin(request({ origin: 'https://evil.example', host: 'mercure.localhost' }))).toBe(false);
    expect(isSameOrigin(request({ origin: 'null', host: 'mercure.localhost' }))).toBe(false);
    expect(isSameOrigin(request({ host: 'mercure.localhost' }))).toBe(false);
  });
});

describe('publicUrl', () => {
  it("reconstruit l'URL publique depuis l'hôte et le schéma transmis par la passerelle", () => {
    const r = request({
      host: 'backoffice:3000',
      'x-forwarded-host': 'mercure.localhost:8265',
      'x-forwarded-proto': 'http',
    });
    expect(publicUrl(r, '/login?erreur=1').toString()).toBe('http://mercure.localhost:8265/login?erreur=1');
  });

  it("retombe sur l'hôte reçu et http sans en-têtes de passerelle", () => {
    expect(publicUrl(request({ host: 'mercure.localhost' }), '/').toString()).toBe(
      'http://mercure.localhost/'
    );
  });

  it('refuse un hôte ou un schéma douteux', () => {
    const evil = request({
      host: 'mercure.localhost',
      'x-forwarded-host': 'evil.example/..',
      'x-forwarded-proto': 'javascript',
    });
    expect(publicUrl(evil, '/').toString()).toBe('http://mercure.localhost/');
  });
});

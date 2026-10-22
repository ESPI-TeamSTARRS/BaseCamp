import { afterEach, describe, expect, it, vi } from 'vitest';
import { COMPLETE_PATH, completeInvitation } from '../invitation-api';

function respond(status: number, body: unknown = {}) {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe('completeInvitation', () => {
  it('envoie jeton, mot de passe et images sans cookie ni référent', async () => {
    const fetchMock = respond(201, { created: true });

    expect(await completeInvitation('tok', 'secret-pass-phrase', ['a', 'b', 'c'])).toBe('created');

    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe(COMPLETE_PATH);
    expect(init).toMatchObject({ method: 'POST', credentials: 'omit', referrerPolicy: 'no-referrer' });
    expect(JSON.parse(init.body)).toEqual({
      token: 'tok',
      password: 'secret-pass-phrase',
      images: ['a', 'b', 'c'],
    });
  });

  it('401 : lien invalide, expiré, utilisé ou inconnu (un seul cas)', async () => {
    respond(401, { detail: 'Invitation invalide ou expirée.' });
    expect(await completeInvitation('t', 'p', [])).toBe('invalid_link');
  });

  it.each([
    ['password_too_short', 'weak_password'],
    ['password_too_long', 'weak_password'],
    ['password_too_common', 'weak_password'],
    ['photo_count', 'photo_count'],
    ['invalid_photo', 'invalid_photo'],
    ['no_face', 'no_face'],
  ])('422 %s -> %s', async (code, expected) => {
    respond(422, { detail: 'x', code });
    expect(await completeInvitation('t', 'p', [])).toBe(expected);
  });

  it.each([
    ['422 inconnu', 422, { code: 'autre' }],
    ['422 illisible', 422, null],
    ['500', 500, {}],
    ['429', 429, {}],
  ])('%s -> erreur générique', async (_name, status, body) => {
    respond(status, body);
    expect(await completeInvitation('t', 'p', [])).toBe('error');
  });

  it('une panne réseau est une erreur générique', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network')));
    expect(await completeInvitation('t', 'p', [])).toBe('error');
  });
});

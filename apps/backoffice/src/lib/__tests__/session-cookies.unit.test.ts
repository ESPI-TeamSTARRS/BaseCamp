import { describe, expect, it } from 'vitest';
import { ACCESS_COOKIE, expiredCookie, sessionCookie } from '../session-cookies';

describe('cookie de session', () => {
  it('est HttpOnly, SameSite=Strict et valable sur tout le back-office', () => {
    const cookie = sessionCookie(ACCESS_COOKIE, 'jeton', { maxAge: 900, secure: false });

    expect(cookie).toMatchObject({
      name: 'bo_access',
      httpOnly: true,
      sameSite: 'strict',
      path: '/',
      maxAge: 900,
      secure: false,
    });
    expect(sessionCookie(ACCESS_COOKIE, 'jeton', { maxAge: 900, secure: true }).secure).toBe(true);
  });

  it('s’efface avec la même portée et une durée nulle', () => {
    expect(expiredCookie(ACCESS_COOKIE, true)).toMatchObject({
      value: '',
      maxAge: 0,
      path: '/',
      httpOnly: true,
      secure: true,
    });
  });
});

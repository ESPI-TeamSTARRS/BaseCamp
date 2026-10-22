// Cookie de session du back-office : le jeton d'acces d'`auth`, HttpOnly (illisible par le script) et
// SameSite=Strict. Aucun jeton n'est jamais dans un stockage du navigateur, une URL ou une page.
// Le jeton du back-office n'a pas de jeton de rafraichissement : a l'expiration, on se reconnecte.

export const ACCESS_COOKIE = 'bo_access';

export interface CookieSpec {
  name: string;
  value: string;
  httpOnly: true;
  sameSite: 'strict';
  secure: boolean;
  path: '/';
  maxAge: number;
}

export function sessionCookie(
  name: string,
  value: string,
  options: { maxAge: number; secure: boolean }
): CookieSpec {
  return {
    name,
    value,
    httpOnly: true,
    sameSite: 'strict',
    secure: options.secure,
    path: '/',
    maxAge: options.maxAge,
  };
}

export function expiredCookie(name: string, secure: boolean): CookieSpec {
  return sessionCookie(name, '', { maxAge: 0, secure });
}

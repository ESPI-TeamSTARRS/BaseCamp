import type { NextResponse } from 'next/server';
import { ACCESS_COOKIE, expiredCookie, sessionCookie } from './session-cookies';

export function setSession(
  response: NextResponse,
  accessToken: string,
  expiresIn: number,
  secure: boolean
): NextResponse {
  response.cookies.set(sessionCookie(ACCESS_COOKIE, accessToken, { maxAge: expiresIn, secure }));
  return response;
}

export function clearSession(response: NextResponse, secure: boolean): NextResponse {
  response.cookies.set(expiredCookie(ACCESS_COOKIE, secure));
  return response;
}

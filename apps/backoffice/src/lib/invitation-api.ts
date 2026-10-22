// Appel du navigateur vers la creation du compte par invitation (route publique d'auth, origine admin).
// Aucun detail serveur n'est relaye : seulement une categorie, jamais le jeton ni le mot de passe.

export const COMPLETE_PATH = '/api/auth/backoffice/invitation/complete';

export type CompleteResult =
  'created' | 'invalid_link' | 'weak_password' | 'photo_count' | 'invalid_photo' | 'no_face' | 'error';

const PASSWORD_CODES = new Set(['password_too_short', 'password_too_long', 'password_too_common']);
const PHOTO_CODES = new Set(['photo_count', 'invalid_photo', 'no_face']);

export async function completeInvitation(
  token: string,
  password: string,
  images: string[]
): Promise<CompleteResult> {
  let response: Response;
  try {
    response = await fetch(COMPLETE_PATH, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'omit',
      cache: 'no-store',
      referrerPolicy: 'no-referrer',
      body: JSON.stringify({ token, password, images }),
    });
  } catch {
    return 'error';
  }
  if (response.status === 201) return 'created';
  if (response.status === 401) return 'invalid_link';
  if (response.status === 422) {
    const data = (await response.json().catch(() => null)) as { code?: unknown } | null;
    const code = typeof data?.code === 'string' ? data.code : '';
    if (PASSWORD_CODES.has(code)) return 'weak_password';
    if (PHOTO_CODES.has(code)) return code as CompleteResult;
  }
  return 'error';
}

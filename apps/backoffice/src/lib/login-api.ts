// Appels du navigateur vers les routes serveur du back-office (/session/*), qui relaient vers auth
// et posent les cookies HttpOnly. Aucun score, aucun detail : seulement reconnu ou non.

export type IdentifyResult = { kind: 'ok'; challengeId: string; expiresIn: number } | { kind: 'error' };
export type FaceResult = 'accepted' | 'refused' | 'invalid_image' | 'error';
export type PasswordResult = 'success' | 'refused' | 'error';

async function post(path: string, body: unknown): Promise<Response | null> {
  try {
    return await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      cache: 'no-store',
      body: JSON.stringify(body),
    });
  } catch {
    return null;
  }
}

export async function identify(email: string): Promise<IdentifyResult> {
  const response = await post('/session/identify', { email });
  if (!response?.ok) return { kind: 'error' };
  const data = (await response.json().catch(() => null)) as {
    challenge_id?: unknown;
    expires_in?: unknown;
  } | null;
  if (typeof data?.challenge_id !== 'string' || typeof data.expires_in !== 'number') return { kind: 'error' };
  return { kind: 'ok', challengeId: data.challenge_id, expiresIn: data.expires_in };
}

export async function submitFace(challengeId: string, images: string[]): Promise<FaceResult> {
  const response = await post('/session/face', { challenge_id: challengeId, images });
  if (response?.status === 200) return 'accepted';
  if (response?.status === 401) return 'refused';
  if (response?.status === 422) return 'invalid_image';
  return 'error';
}

export async function submitPassword(challengeId: string, password: string): Promise<PasswordResult> {
  const response = await post('/session/password', { challenge_id: challengeId, password });
  if (response?.status === 200) return 'success';
  if (response?.status === 401) return 'refused';
  return 'error';
}

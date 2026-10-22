// Acces a la camera du navigateur (getUserMedia exige HTTPS ou localhost).

export type CameraFailure = 'denied' | 'absent' | 'unsupported' | 'unavailable';
export type CameraResult = { kind: 'ok'; stream: MediaStream } | { kind: 'error'; reason: CameraFailure };

function failureOf(error: unknown): CameraFailure {
  const name = error instanceof Error ? error.name : '';
  if (name === 'NotAllowedError' || name === 'SecurityError') return 'denied';
  if (name === 'NotFoundError' || name === 'OverconstrainedError') return 'absent';
  return 'unavailable';
}

export async function startCamera(): Promise<CameraResult> {
  const devices = navigator.mediaDevices;
  if (!devices?.getUserMedia) return { kind: 'error', reason: 'unsupported' };
  try {
    const stream = await devices.getUserMedia({ video: { facingMode: 'user' }, audio: false });
    return { kind: 'ok', stream };
  } catch (error) {
    return { kind: 'error', reason: failureOf(error) };
  }
}

/** Arrete chaque piste : c'est ce qui eteint le voyant de la camera. */
export function stopCamera(stream: MediaStream | null): void {
  stream?.getTracks().forEach((track) => track.stop());
}

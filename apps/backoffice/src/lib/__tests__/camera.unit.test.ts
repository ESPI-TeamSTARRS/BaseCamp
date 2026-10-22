import { afterEach, describe, expect, it, vi } from 'vitest';
import { startCamera, stopCamera } from '../camera';

function fakeStream() {
  const tracks = [{ stop: vi.fn() }, { stop: vi.fn() }];
  return { stream: { getTracks: () => tracks } as unknown as MediaStream, tracks };
}

function stubMedia(getUserMedia: unknown): void {
  vi.stubGlobal('navigator', { mediaDevices: getUserMedia ? { getUserMedia } : undefined });
}

afterEach(() => vi.unstubAllGlobals());

describe('startCamera', () => {
  it('demande la vidéo seule et renvoie le flux', async () => {
    const { stream } = fakeStream();
    const getUserMedia = vi.fn().mockResolvedValue(stream);
    stubMedia(getUserMedia);
    expect(await startCamera()).toEqual({ kind: 'ok', stream });
    expect(getUserMedia).toHaveBeenCalledWith({ video: { facingMode: 'user' }, audio: false });
  });

  it.each([
    ['NotAllowedError', 'denied'],
    ['SecurityError', 'denied'],
    ['NotFoundError', 'absent'],
    ['NotReadableError', 'unavailable'],
    ['Autre', 'unavailable'],
  ])('traduit %s en %s', async (name, reason) => {
    stubMedia(vi.fn().mockRejectedValue(Object.assign(new Error('x'), { name })));
    expect(await startCamera()).toEqual({ kind: 'error', reason });
  });

  it('signale une caméra non prise en charge (pas de getUserMedia)', async () => {
    stubMedia(undefined);
    expect(await startCamera()).toEqual({ kind: 'error', reason: 'unsupported' });
  });
});

describe('stopCamera', () => {
  it('arrête toutes les pistes du flux', () => {
    const { stream, tracks } = fakeStream();
    stopCamera(stream);
    tracks.forEach((track) => expect(track.stop).toHaveBeenCalledTimes(1));
  });

  it('accepte l’absence de flux', () => {
    expect(() => stopCamera(null)).not.toThrow();
  });
});

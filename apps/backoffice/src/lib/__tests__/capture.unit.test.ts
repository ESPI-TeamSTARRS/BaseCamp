// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MAX_FRAME_WIDTH, captureFrames } from '../capture';

function stubCanvas(dataUrl: string, context: object | null = { drawImage: vi.fn() }) {
  const canvas = { width: 0, height: 0, getContext: vi.fn(() => context), toDataURL: vi.fn(() => dataUrl) };
  vi.spyOn(document, 'createElement').mockReturnValue(canvas as unknown as HTMLElement);
  return canvas;
}

function video(width: number, height: number): HTMLVideoElement {
  return { videoWidth: width, videoHeight: height } as HTMLVideoElement;
}

afterEach(() => vi.restoreAllMocks());

describe('captureFrames', () => {
  it('capture le nombre d’images demandé, en base64 JPEG sans préfixe', async () => {
    const canvas = stubCanvas('data:image/jpeg;base64,QUJD');
    const frames = await captureFrames(video(640, 480), 3, 0);
    expect(frames).toEqual(['QUJD', 'QUJD', 'QUJD']);
    expect(canvas.toDataURL).toHaveBeenCalledWith('image/jpeg', expect.any(Number));
  });

  it('réduit les images plus larges que la limite', async () => {
    const canvas = stubCanvas('data:image/jpeg;base64,QUJD');
    await captureFrames(video(1920, 1080), 1, 0);
    expect(canvas.width).toBe(MAX_FRAME_WIDTH);
    expect(canvas.height).toBe(Math.round((1080 * MAX_FRAME_WIDTH) / 1920));
  });

  it('échoue si le contexte 2D est indisponible', async () => {
    stubCanvas('data:image/jpeg;base64,QUJD', null);
    await expect(captureFrames(video(640, 480), 1, 0)).rejects.toThrow();
  });

  it('échoue si la vidéo n’a pas encore d’image', async () => {
    stubCanvas('data:image/jpeg;base64,QUJD');
    await expect(captureFrames(video(0, 0), 1, 0)).rejects.toThrow();
  });
});

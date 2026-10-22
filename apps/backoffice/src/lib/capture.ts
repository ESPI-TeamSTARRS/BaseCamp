// Capture d'images de l'apercu video : JPEG en base64 sans prefixe, reduites pour rester sous 1 Mo.

export const MAX_FRAME_WIDTH = 640;
const JPEG_QUALITY = 0.85;

function grabFrame(video: HTMLVideoElement): string {
  if (!video.videoWidth || !video.videoHeight) throw new Error('video_not_ready');
  const scale = Math.min(1, MAX_FRAME_WIDTH / video.videoWidth);
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  const context = canvas.getContext('2d');
  if (!context) throw new Error('canvas_unavailable');
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', JPEG_QUALITY).split(',')[1];
}

export async function captureFrames(
  video: HTMLVideoElement,
  count: number,
  intervalMs = 300
): Promise<string[]> {
  const frames: string[] = [];
  for (let i = 0; i < count; i++) {
    if (i > 0) await new Promise((resolve) => setTimeout(resolve, intervalMs));
    frames.push(grabFrame(video));
  }
  return frames;
}

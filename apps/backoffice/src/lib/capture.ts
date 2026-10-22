// Capture d'images de l'apercu video : JPEG en base64 sans prefixe, reduites pour rester sous 1 Mo.

export const MAX_FRAME_WIDTH = 640;
/** Limite d'une image cote serveur (1 Mo) : l'image est reduite jusqu'a la respecter. */
export const MAX_IMAGE_BYTES = 1_048_576;
const JPEG_QUALITY = 0.85;
const SHRINK_STEPS = 6;

function decodedSize(base64: string): number {
  const padding = base64.endsWith('==') ? 2 : base64.endsWith('=') ? 1 : 0;
  return Math.floor((base64.length * 3) / 4) - padding;
}

/** Une image de l'apercu : largeur et qualite baissent tant que le JPEG depasse 1 Mo. */
export function captureFrame(video: HTMLVideoElement): string {
  if (!video.videoWidth || !video.videoHeight) throw new Error('video_not_ready');
  let scale = Math.min(1, MAX_FRAME_WIDTH / video.videoWidth);
  let quality = JPEG_QUALITY;
  for (let step = 0; step < SHRINK_STEPS; step++) {
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    const context = canvas.getContext('2d');
    if (!context) throw new Error('canvas_unavailable');
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const image = canvas.toDataURL('image/jpeg', quality).split(',')[1];
    if (decodedSize(image) <= MAX_IMAGE_BYTES) return image;
    scale *= 0.75;
    quality = Math.max(0.4, quality - 0.1);
  }
  throw new Error('image_too_large');
}

export async function captureFrames(
  video: HTMLVideoElement,
  count: number,
  intervalMs = 300
): Promise<string[]> {
  const frames: string[] = [];
  for (let i = 0; i < count; i++) {
    if (i > 0) await new Promise((resolve) => setTimeout(resolve, intervalMs));
    frames.push(captureFrame(video));
  }
  return frames;
}

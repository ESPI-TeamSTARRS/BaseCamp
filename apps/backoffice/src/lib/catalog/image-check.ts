// Controle d'une image avant envoi : memes limites que l'API (JPEG, PNG ou WebP, 2 Mio au plus).
// Shop relit le contenu reel du fichier : ce controle n'est qu'un confort de saisie.

export const MAX_IMAGE_BYTES = 2 * 1024 * 1024;
const ACCEPTED = new Set(['image/jpeg', 'image/png', 'image/webp']);

export const IMAGE_RULE = 'JPEG, PNG ou WebP, 2 Mo au plus.';

/** Message de refus clair, ou null si l'image peut etre envoyee. */
export function imageProblem(file: { type: string; size: number }): string | null {
  if (!ACCEPTED.has(file.type)) return `Image refusée : format non pris en charge. ${IMAGE_RULE}`;
  if (file.size === 0) return 'Image refusée : le fichier est vide.';
  if (file.size > MAX_IMAGE_BYTES) return `Image refusée : fichier trop lourd. ${IMAGE_RULE}`;
  return null;
}

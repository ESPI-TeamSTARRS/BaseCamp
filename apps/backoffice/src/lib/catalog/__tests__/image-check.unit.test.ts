import { describe, expect, it } from 'vitest';
import { imageProblem, MAX_IMAGE_BYTES } from '../image-check';

describe('imageProblem', () => {
  it.each(['image/jpeg', 'image/png', 'image/webp'])('accepte %s', (type) => {
    expect(imageProblem({ type, size: 1000 })).toBeNull();
    expect(imageProblem({ type, size: MAX_IMAGE_BYTES })).toBeNull();
  });

  it('refuse un format non pris en charge, un fichier vide ou trop lourd, avec la règle', () => {
    expect(imageProblem({ type: 'image/gif', size: 10 })).toBe(
      'Image refusée : format non pris en charge. JPEG, PNG ou WebP, 2 Mo au plus.'
    );
    expect(imageProblem({ type: '', size: 10 })).toMatch(/format non pris en charge/);
    expect(imageProblem({ type: 'image/png', size: 0 })).toBe('Image refusée : le fichier est vide.');
    expect(imageProblem({ type: 'image/png', size: MAX_IMAGE_BYTES + 1 })).toBe(
      'Image refusée : fichier trop lourd. JPEG, PNG ou WebP, 2 Mo au plus.'
    );
  });
});

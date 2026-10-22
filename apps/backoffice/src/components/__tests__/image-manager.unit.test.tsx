// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ImageManager } from '../image-manager';
import { makeProduct, stubApi } from './stub-api';

const created: string[] = [];
const revoked: string[] = [];

beforeEach(() => {
  vi.stubGlobal(
    'URL',
    Object.assign(URL, {
      createObjectURL: vi.fn(() => {
        const url = `blob:test/${created.length}`;
        created.push(url);
        return url;
      }),
      revokeObjectURL: vi.fn((url: string) => revoked.push(url)),
    })
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  created.length = 0;
  revoked.length = 0;
});

const png = (name = 'photo.png', size = 2000) =>
  new File([new Uint8Array(size)], name, { type: 'image/png' });

describe('ImageManager', () => {
  it('liste les images actuelles avec un texte alternatif, ou indique qu’il n’y en a pas', () => {
    const { rerender } = render(<ImageManager product={makeProduct()} onUpdated={() => undefined} />);
    expect(screen.getByText('Aucune image pour le moment.')).toBeInTheDocument();

    rerender(
      <ImageManager
        product={makeProduct({ image_urls: ['/media/a.png', '/media/b.png'] })}
        onUpdated={() => undefined}
      />
    );

    expect(screen.getByRole('img', { name: 'Image 2 de Tente Tunnel' })).toHaveAttribute(
      'src',
      '/media/b.png'
    );
  });

  it('montre un aperçu avant l’envoi, puis envoie le fichier et signale l’ajout', async () => {
    const updated = makeProduct({ image_urls: ['/media/new.png'], version: 4 });
    const calls = stubApi(() => [200, updated]);
    const onUpdated = vi.fn();
    const user = userEvent.setup();
    render(<ImageManager product={makeProduct()} onUpdated={onUpdated} />);

    await user.upload(screen.getByLabelText('Ajouter une image'), png());

    expect(screen.getByRole('img', { name: 'Aperçu de l’image à envoyer' })).toHaveAttribute(
      'src',
      'blob:test/0'
    );
    expect(calls).toEqual([]);
    await user.click(screen.getByRole('button', { name: 'Envoyer l’image' }));

    expect(await screen.findByText('Image ajoutée.')).toBeInTheDocument();
    expect(onUpdated).toHaveBeenCalledWith(updated);
    expect(calls[0]).toMatchObject({ method: 'POST', path: '/bff/products/tente-tunnel/image' });
    expect(screen.queryByRole('img', { name: 'Aperçu de l’image à envoyer' })).not.toBeInTheDocument();
  });

  it('annule l’aperçu sans rien envoyer et libère l’URL temporaire', async () => {
    const calls = stubApi(() => [200, makeProduct()]);
    const user = userEvent.setup();
    render(<ImageManager product={makeProduct()} onUpdated={() => undefined} />);
    await user.upload(screen.getByLabelText('Ajouter une image'), png());

    await user.click(screen.getByRole('button', { name: 'Annuler' }));

    expect(screen.queryByRole('img', { name: 'Aperçu de l’image à envoyer' })).not.toBeInTheDocument();
    expect(calls).toEqual([]);
    expect(revoked).toContain('blob:test/0');
  });

  it('refuse clairement un format non pris en charge, sans aperçu ni envoi', async () => {
    const calls = stubApi(() => [200, makeProduct()]);
    const user = userEvent.setup({ applyAccept: false });
    render(<ImageManager product={makeProduct()} onUpdated={() => undefined} />);

    await user.upload(
      screen.getByLabelText('Ajouter une image'),
      new File(['GIF89a'], 'anim.gif', { type: 'image/gif' })
    );

    expect(screen.getByRole('alert')).toHaveTextContent(
      'Image refusée : format non pris en charge. JPEG, PNG ou WebP, 2 Mo au plus.'
    );
    expect(screen.queryByRole('button', { name: 'Envoyer l’image' })).not.toBeInTheDocument();
    expect(calls).toEqual([]);
  });

  it('refuse un fichier trop lourd ou vide', async () => {
    const user = userEvent.setup();
    render(<ImageManager product={makeProduct()} onUpdated={() => undefined} />);
    const input = screen.getByLabelText('Ajouter une image');

    await user.upload(input, png('lourde.png', 2 * 1024 * 1024 + 1));
    expect(screen.getByRole('alert')).toHaveTextContent('fichier trop lourd');
    await user.upload(input, png('vide.png', 0));
    expect(screen.getByRole('alert')).toHaveTextContent('le fichier est vide');
  });

  it('affiche le refus du serveur et garde l’aperçu pour réessayer', async () => {
    stubApi(() => [422, { detail: 'Image refusée : JPEG, PNG ou WebP, 2 Mo au plus.', code: 'invalid' }]);
    const user = userEvent.setup();
    render(<ImageManager product={makeProduct()} onUpdated={() => undefined} />);
    await user.upload(screen.getByLabelText('Ajouter une image'), png());

    await user.click(screen.getByRole('button', { name: 'Envoyer l’image' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Image refusée : JPEG, PNG ou WebP, 2 Mo au plus.'
    );
    expect(screen.getByRole('button', { name: 'Envoyer l’image' })).toBeEnabled();
  });

  it('n’offre plus d’ajout quand le maximum de dix images est atteint', () => {
    const urls = Array.from({ length: 10 }, (_, index) => `/media/${index}.png`);

    render(<ImageManager product={makeProduct({ image_urls: urls })} onUpdated={() => undefined} />);

    expect(screen.getByText('Le nombre maximal d’images (10) est atteint.')).toBeInTheDocument();
    expect(screen.queryByLabelText('Ajouter une image')).not.toBeInTheDocument();
  });

  it('vide la sélection quand on retire le fichier choisi', async () => {
    const user = userEvent.setup();
    render(<ImageManager product={makeProduct()} onUpdated={() => undefined} />);
    const input = screen.getByLabelText('Ajouter une image');
    await user.upload(input, png());

    fireEvent.change(input, { target: { files: [] } });

    expect(screen.queryByRole('button', { name: 'Envoyer l’image' })).not.toBeInTheDocument();
  });
});

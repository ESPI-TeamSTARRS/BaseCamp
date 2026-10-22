// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ArchivePanel } from '../archive-panel';
import { makeProduct, stubApi } from './stub-api';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ArchivePanel', () => {
  it('demande une confirmation explicite, avec le focus sur Annuler, et n’archive rien avant', async () => {
    const calls = stubApi(() => [200, makeProduct()]);
    const user = userEvent.setup();
    render(<ArchivePanel product={makeProduct()} onArchived={() => undefined} />);

    await user.click(screen.getByRole('button', { name: 'Archiver ce produit' }));

    const dialog = screen.getByRole('alertdialog', { name: 'Archiver « Tente Tunnel » ?' });
    expect(dialog).toHaveAccessibleDescription(/disparaîtra du site client/);
    expect(screen.getByRole('button', { name: 'Annuler' })).toHaveFocus();
    expect(calls).toEqual([]);
  });

  it('annule sans appeler l’API', async () => {
    const calls = stubApi(() => [200, makeProduct()]);
    const user = userEvent.setup();
    render(<ArchivePanel product={makeProduct()} onArchived={() => undefined} />);
    await user.click(screen.getByRole('button', { name: 'Archiver ce produit' }));

    await user.click(screen.getByRole('button', { name: 'Annuler' }));

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(calls).toEqual([]);
  });

  it('archive puis transmet le produit archivé', async () => {
    const archived = makeProduct({ archived_at: '2026-10-22T00:00:00Z' });
    const calls = stubApi(() => [200, archived]);
    const onArchived = vi.fn();
    const user = userEvent.setup();
    render(<ArchivePanel product={makeProduct()} onArchived={onArchived} />);
    await user.click(screen.getByRole('button', { name: 'Archiver ce produit' }));

    await user.click(screen.getByRole('button', { name: 'Confirmer l’archivage' }));

    await vi.waitFor(() => expect(onArchived).toHaveBeenCalledWith(archived));
    expect(calls[0]).toMatchObject({ method: 'POST', path: '/bff/products/tente-tunnel/archive' });
  });

  it('affiche le motif quand l’archivage échoue et laisse réessayer', async () => {
    stubApi(() => [
      503,
      {
        detail: 'Le catalogue est momentanément indisponible. Réessayez dans un instant.',
        code: 'unavailable',
      },
    ]);
    const onArchived = vi.fn();
    const user = userEvent.setup();
    render(<ArchivePanel product={makeProduct()} onArchived={onArchived} />);
    await user.click(screen.getByRole('button', { name: 'Archiver ce produit' }));

    await user.click(screen.getByRole('button', { name: 'Confirmer l’archivage' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('momentanément indisponible');
    expect(screen.getByRole('button', { name: 'Confirmer l’archivage' })).toBeEnabled();
    expect(onArchived).not.toHaveBeenCalled();
  });
});

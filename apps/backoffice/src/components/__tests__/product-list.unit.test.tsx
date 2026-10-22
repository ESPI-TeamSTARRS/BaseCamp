// @vitest-environment jsdom
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ProductList } from '../product-list';
import { makeProduct, page, stubApi } from './stub-api';

afterEach(() => {
  vi.unstubAllGlobals();
});

const TENTE = makeProduct({ image_urls: ['/media/product-images/a.png'] });
const GOURDE = makeProduct({
  id: 'gourde',
  name: 'Gourde inox',
  category: 'cuisine',
  price_cents: 1500,
  stock: 3,
  availability: 'low_stock',
});

describe('ProductList', () => {
  it('annonce le chargement puis affiche le tableau accessible des produits', async () => {
    stubApi(() => [200, page([TENTE, GOURDE])]);

    render(<ProductList />);

    expect(screen.getByRole('status')).toHaveTextContent('Chargement du catalogue…');
    const table = await screen.findByRole('table', { name: 'Produits du catalogue' });
    const rows = within(table).getAllByRole('row');
    expect(rows).toHaveLength(3);
    expect(within(rows[1]).getByRole('link', { name: 'Tente Tunnel' })).toHaveAttribute(
      'href',
      '/produits/tente-tunnel'
    );
    expect(rows[1]).toHaveTextContent('Tentes');
    expect(rows[1]).toHaveTextContent('129,90');
    expect(rows[1]).toHaveTextContent('En stock');
    expect(rows[2]).toHaveTextContent('Stock faible');
    expect(screen.getByRole('status')).toHaveTextContent('Produits 1 à 2 sur 2');
    expect(rows[1].querySelector('img')).toHaveAttribute('src', '/media/product-images/a.png');
    expect(within(rows[2]).getByRole('img', { name: 'Aucune image' })).toBeInTheDocument();
  });

  it('recherche par nom et revient à la première page', async () => {
    const calls = stubApi(() => [200, page([TENTE])]);
    const user = userEvent.setup();
    render(<ProductList />);
    await screen.findByRole('table');

    await user.type(screen.getByLabelText('Rechercher un produit par nom'), 'tunnel');
    await user.click(screen.getByRole('button', { name: 'Rechercher' }));

    await waitFor(() => expect(calls.at(-1)?.path).toBe('/bff/products?limit=20&offset=0&q=tunnel'));
  });

  it('affiche un message dédié quand la recherche ne donne rien et permet de l’effacer', async () => {
    const calls = stubApi((call) => [200, call.path.includes('q=zzz') ? page([], 0) : page([TENTE])]);
    const user = userEvent.setup();
    render(<ProductList />);
    await screen.findByRole('table');

    await user.type(screen.getByLabelText('Rechercher un produit par nom'), 'zzz{Enter}');
    expect(await screen.findByText('Aucun produit ne correspond à « zzz ».')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Effacer la recherche' }));

    expect(await screen.findByRole('table')).toBeInTheDocument();
    expect(screen.getByLabelText('Rechercher un produit par nom')).toHaveValue('');
    expect(calls.at(-1)?.path).toBe('/bff/products?limit=20&offset=0');
  });

  it('invite à créer le premier produit quand le catalogue est vide', async () => {
    stubApi(() => [200, page([], 0)]);

    render(<ProductList />);

    expect(await screen.findByText(/Le catalogue est vide/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Créer le premier produit' })).toHaveAttribute(
      'href',
      '/produits/nouveau'
    );
  });

  it('affiche l’erreur avec un bouton Réessayer qui relance la requête', async () => {
    let up = false;
    stubApi(() =>
      up
        ? [200, page([TENTE])]
        : [
            503,
            {
              detail: 'Le catalogue est momentanément indisponible. Réessayez dans un instant.',
              code: 'unavailable',
            },
          ]
    );
    const user = userEvent.setup();
    render(<ProductList />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('momentanément indisponible');
    up = true;
    await user.click(within(alert).getByRole('button', { name: 'Réessayer' }));

    expect(await screen.findByRole('table')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('filtre les produits archivés et les signale', async () => {
    const archived = makeProduct({ id: 'vieux', name: 'Vieux réchaud', archived_at: '2026-10-01T00:00:00Z' });
    const calls = stubApi((call) => [
      200,
      page(call.path.includes('include_archived=true') ? [TENTE, archived] : [TENTE]),
    ]);
    const user = userEvent.setup();
    render(<ProductList />);
    await screen.findByRole('table');
    expect(screen.queryByText('Vieux réchaud')).not.toBeInTheDocument();

    await user.click(screen.getByRole('checkbox', { name: 'Afficher les produits archivés' }));

    const row = (await screen.findByText('Vieux réchaud')).closest('tr') as HTMLElement;
    expect(within(row).getByText('Archivé')).toBeInTheDocument();
    expect(calls.at(-1)?.path).toContain('include_archived=true');
  });

  it('pagine : page suivante puis précédente, boutons désactivés aux extrémités', async () => {
    const calls = stubApi((call) => {
      const offset = Number(new URLSearchParams(call.path.split('?')[1]).get('offset'));
      return [200, page([makeProduct({ id: `p${offset}`, name: `Produit ${offset}` })], 45, offset)];
    });
    const user = userEvent.setup();
    render(<ProductList />);
    await screen.findByRole('table');
    expect(screen.getByRole('button', { name: 'Page précédente' })).toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'Page suivante' }));
    expect(await screen.findByText('Produit 20')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Page suivante' }));
    expect(await screen.findByText('Produit 40')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Page suivante' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Page précédente' }));
    expect(await screen.findByText('Produit 20')).toBeInTheDocument();
    expect(calls.map((c) => c.path.match(/offset=(\d+)/)?.[1])).toEqual(['0', '20', '40', '20']);
  });

  it('propose la création d’un produit', async () => {
    stubApi(() => [200, page([TENTE])]);

    render(<ProductList />);

    expect(await screen.findByRole('link', { name: 'Nouveau produit' })).toHaveAttribute(
      'href',
      '/produits/nouveau'
    );
  });
});

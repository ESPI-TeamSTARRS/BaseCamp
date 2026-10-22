// @vitest-environment jsdom
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { OrderDetailView } from '../order-detail';
import { makeDetail } from './order-stub';
import { stubApi } from './stub-api';

afterEach(() => {
  vi.unstubAllGlobals();
});

const ID = '00000000-0000-4000-8000-000000000001';

describe('OrderDetailView', () => {
  it('annonce le chargement puis affiche numéro, statut, client, lignes, totaux et adresse', async () => {
    const calls = stubApi(() => [200, makeDetail()]);

    render(<OrderDetailView orderId={ID} />);

    expect(screen.getByRole('status')).toHaveTextContent('Chargement de la commande…');
    expect(await screen.findByRole('heading', { level: 2, name: 'Commande BC-1001' })).toBeInTheDocument();
    expect(calls[0].path).toBe(`/bff/orders/${ID}`);
    expect(screen.getByText('Payée')).toBeInTheDocument();
    expect(screen.getByText('camille.martin@example.org')).toBeInTheDocument();
    expect(screen.getByText('20 oct. 2026, 12:00')).toBeInTheDocument();

    const lines = screen.getByRole('table', { name: 'Articles de la commande' });
    const row = within(lines).getAllByRole('row')[1];
    expect(row).toHaveTextContent('Popote');
    expect(row).toHaveTextContent('39,00');
    expect(row).toHaveTextContent('78,00');

    const totals = screen.getByRole('region', { name: 'Totaux' });
    expect(totals).toHaveTextContent('Sous-total');
    expect(totals).toHaveTextContent('78,00');
    expect(totals).toHaveTextContent('Livraison');
    expect(totals).toHaveTextContent('4,90');
    expect(totals).toHaveTextContent('Total');
    expect(totals).toHaveTextContent('82,90');

    const address = screen.getByRole('region', { name: 'Adresse de livraison' });
    expect(address).toHaveTextContent('Camille Martin');
    expect(address).toHaveTextContent('12 rue des Alpes');
    expect(address).toHaveTextContent('Bâtiment B');
    expect(address).toHaveTextContent('38000 Grenoble');
    expect(address).toHaveTextContent('FR');
  });

  it('propose le retour à la liste et n’offre aucune action d’écriture', async () => {
    stubApi(() => [200, makeDetail()]);

    render(<OrderDetailView orderId={ID} />);

    expect(await screen.findByRole('link', { name: '← Retour aux commandes' })).toHaveAttribute(
      'href',
      '/commandes'
    );
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('omet la seconde ligne d’adresse quand elle est absente', async () => {
    stubApi(() => [
      200,
      makeDetail({
        shipping_address: {
          full_name: 'Camille Martin',
          line1: '12 rue des Alpes',
          line2: null,
          postal_code: '38000',
          city: 'Grenoble',
          country: 'FR',
        },
      }),
    ]);

    render(<OrderDetailView orderId={ID} />);

    const address = await screen.findByRole('region', { name: 'Adresse de livraison' });
    expect(address).not.toHaveTextContent('Bâtiment');
  });

  it('commande introuvable : message fixe et retour à la liste, sans Réessayer', async () => {
    stubApi(() => [404, { detail: 'Commande introuvable.', code: 'not_found' }]);

    render(<OrderDetailView orderId={ID} />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Commande introuvable.');
    expect(within(alert).queryByRole('button', { name: 'Réessayer' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '← Retour aux commandes' })).toBeInTheDocument();
  });

  it('autre erreur : bouton Réessayer qui relance la requête', async () => {
    let up = false;
    stubApi(() =>
      up
        ? [200, makeDetail()]
        : [
            503,
            {
              detail: 'Les commandes sont momentanément indisponibles. Réessayez dans un instant.',
              code: 'unavailable',
            },
          ]
    );
    const user = userEvent.setup();
    render(<OrderDetailView orderId={ID} />);

    const alert = await screen.findByRole('alert');
    up = true;
    await user.click(within(alert).getByRole('button', { name: 'Réessayer' }));

    expect(await screen.findByRole('heading', { level: 2, name: 'Commande BC-1001' })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

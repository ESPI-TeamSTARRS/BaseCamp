// @vitest-environment jsdom
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { OrderList } from '../order-list';
import { makeSummary, ordersPage } from './order-stub';
import { stubApi } from './stub-api';

afterEach(() => {
  vi.unstubAllGlobals();
});

const PAYEE = makeSummary();
const ATTENTE = makeSummary({
  id: '00000000-0000-4000-8000-000000000002',
  number: 'BC-1002',
  status: 'pending_payment',
  email: 'autre@example.org',
  total_cents: 3900,
  item_count: 1,
});

describe('OrderList', () => {
  it('annonce le chargement puis affiche le tableau accessible des commandes', async () => {
    stubApi(() => [200, ordersPage([PAYEE, ATTENTE])]);

    render(<OrderList />);

    expect(screen.getByRole('status')).toHaveTextContent('Chargement des commandes…');
    const table = await screen.findByRole('table', { name: 'Commandes clients' });
    const rows = within(table).getAllByRole('row');
    expect(rows).toHaveLength(3);
    expect(within(rows[1]).getByRole('link', { name: 'BC-1001' })).toHaveAttribute(
      'href',
      '/commandes/00000000-0000-4000-8000-000000000001'
    );
    expect(rows[1]).toHaveTextContent('camille.martin@example.org');
    expect(rows[1]).toHaveTextContent('82,90');
    expect(rows[1]).toHaveTextContent('Payée');
    expect(rows[1]).toHaveTextContent('20 oct. 2026');
    expect(rows[2]).toHaveTextContent('En attente de paiement');
    expect(screen.getByRole('status')).toHaveTextContent('Commandes 1 à 2 sur 2');
  });

  it('charge 20 commandes par page, de la plus récente à la plus ancienne (ordre de shop)', async () => {
    const calls = stubApi(() => [200, ordersPage([PAYEE])]);

    render(<OrderList />);
    await screen.findByRole('table');

    expect(calls[0].path).toBe('/bff/orders?limit=20&offset=0');
  });

  it('recherche par numéro ou e-mail et revient à la première page', async () => {
    const calls = stubApi(() => [200, ordersPage([PAYEE])]);
    const user = userEvent.setup();
    render(<OrderList />);
    await screen.findByRole('table');

    await user.type(screen.getByLabelText('Rechercher par numéro ou e-mail'), 'BC-1001');
    await user.click(screen.getByRole('button', { name: 'Rechercher' }));

    await waitFor(() => expect(calls.at(-1)?.path).toBe('/bff/orders?limit=20&offset=0&q=BC-1001'));
  });

  it('filtre par statut', async () => {
    const calls = stubApi(() => [200, ordersPage([PAYEE])]);
    const user = userEvent.setup();
    render(<OrderList />);
    await screen.findByRole('table');

    const select = screen.getByLabelText('Statut');
    expect(
      within(select)
        .getAllByRole('option')
        .map((o) => o.textContent)
    ).toEqual(['Tous les statuts', 'En attente de paiement', 'Payée', 'Expirée', 'Remboursée']);
    await user.selectOptions(select, 'refunded');

    await waitFor(() => expect(calls.at(-1)?.path).toBe('/bff/orders?limit=20&offset=0&status=refunded'));
  });

  it('affiche un message dédié quand les critères ne donnent rien et permet de les effacer', async () => {
    const calls = stubApi((call) => [
      200,
      call.path.includes('q=zzz') ? ordersPage([], 0) : ordersPage([PAYEE]),
    ]);
    const user = userEvent.setup();
    render(<OrderList />);
    await screen.findByRole('table');

    await user.type(screen.getByLabelText('Rechercher par numéro ou e-mail'), 'zzz{Enter}');
    expect(await screen.findByText('Aucune commande ne correspond à ces critères.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Effacer les filtres' }));

    expect(await screen.findByRole('table')).toBeInTheDocument();
    expect(screen.getByLabelText('Rechercher par numéro ou e-mail')).toHaveValue('');
    expect(screen.getByLabelText('Statut')).toHaveValue('');
    expect(calls.at(-1)?.path).toBe('/bff/orders?limit=20&offset=0');
  });

  it('annonce l’absence de commande quand il n’y en a aucune', async () => {
    stubApi(() => [200, ordersPage([], 0)]);

    render(<OrderList />);

    expect(await screen.findByText('Aucune commande pour le moment.')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('affiche l’erreur avec un bouton Réessayer qui relance la requête', async () => {
    let up = false;
    stubApi(() =>
      up
        ? [200, ordersPage([PAYEE])]
        : [
            503,
            {
              detail: 'Les commandes sont momentanément indisponibles. Réessayez dans un instant.',
              code: 'unavailable',
            },
          ]
    );
    const user = userEvent.setup();
    render(<OrderList />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('momentanément indisponibles');
    up = true;
    await user.click(within(alert).getByRole('button', { name: 'Réessayer' }));

    expect(await screen.findByRole('table')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('pagine : page suivante puis précédente, boutons désactivés aux extrémités', async () => {
    const calls = stubApi((call) => {
      const offset = Number(new URLSearchParams(call.path.split('?')[1]).get('offset'));
      return [200, ordersPage([makeSummary({ id: `o${offset}`, number: `BC-${offset}` })], 45, offset)];
    });
    const user = userEvent.setup();
    render(<OrderList />);
    await screen.findByRole('table');
    expect(screen.getByRole('button', { name: 'Page précédente' })).toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'Page suivante' }));
    expect(await screen.findByText('BC-20')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Page suivante' }));
    expect(await screen.findByText('BC-40')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Page suivante' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Page précédente' }));
    expect(await screen.findByText('BC-20')).toBeInTheDocument();
    expect(calls.map((c) => c.path.match(/offset=(\d+)/)?.[1])).toEqual(['0', '20', '40', '20']);
  });
});

// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import OrderDetailPage from '../commandes/[id]/page';
import OrdersPage from '../commandes/page';
import HomePage from '../page';
import { makeDetail, makeSummary, ordersPage } from '@/components/__tests__/order-stub';
import { PageShell } from '@/components/page-shell';
import { stubApi } from '@/components/__tests__/stub-api';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('écrans des commandes', () => {
  it('la liste est titrée « Commandes » et charge les commandes', async () => {
    stubApi(() => [200, ordersPage([makeSummary()])]);

    render(<OrdersPage />);

    expect(screen.getByRole('heading', { level: 1, name: 'Commandes' })).toBeInTheDocument();
    expect(await screen.findByRole('table')).toBeInTheDocument();
  });

  it('le détail charge la commande de l’adresse', async () => {
    const calls = stubApi(() => [200, makeDetail()]);

    render(await OrderDetailPage({ params: Promise.resolve({ id: 'cmd-1' }) }));

    expect(await screen.findByRole('heading', { level: 2, name: 'Commande BC-1001' })).toBeInTheDocument();
    expect(calls[0].path).toBe('/bff/orders/cmd-1');
    expect(screen.getByRole('heading', { level: 1, name: 'Détail de la commande' })).toBeInTheDocument();
  });

  it('la navigation et l’accueil mènent aux commandes', () => {
    render(<PageShell title="x">contenu</PageShell>);
    expect(screen.getByRole('link', { name: 'Commandes' })).toHaveAttribute('href', '/commandes');
    expect(screen.getByRole('link', { name: 'Catalogue' })).toHaveAttribute('href', '/produits');
  });

  it('l’accueil propose de consulter les commandes', () => {
    render(<HomePage />);

    expect(screen.getAllByRole('link', { name: 'Consulter les commandes' })[0]).toHaveAttribute(
      'href',
      '/commandes'
    );
  });
});

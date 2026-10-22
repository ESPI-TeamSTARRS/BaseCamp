// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import HomePage from '../page';
import EditProductPage from '../produits/[id]/page';
import NewProductPage from '../produits/nouveau/page';
import ProductsPage from '../produits/page';
import { makeProduct, page, stubApi } from '@/components/__tests__/stub-api';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('écrans du catalogue', () => {
  it('l’accueil mène au catalogue et propose la déconnexion', () => {
    render(<HomePage />);

    expect(screen.getByRole('link', { name: 'Gérer le catalogue' })).toHaveAttribute('href', '/produits');
    expect(screen.getByRole('button', { name: 'Se déconnecter' })).toBeInTheDocument();
  });

  it('la liste est titrée « Catalogue » et charge les produits', async () => {
    stubApi(() => [200, page([makeProduct()])]);

    render(<ProductsPage />);

    expect(screen.getByRole('heading', { level: 1, name: 'Catalogue' })).toBeInTheDocument();
    expect(await screen.findByRole('table')).toBeInTheDocument();
  });

  it('la création affiche le formulaire vide', () => {
    render(<NewProductPage />);

    expect(screen.getByRole('heading', { level: 1, name: 'Nouveau produit' })).toBeInTheDocument();
    expect(screen.getByLabelText('Nom')).toHaveValue('');
  });

  it('la modification charge le produit de l’adresse', async () => {
    const calls = stubApi(() => [200, makeProduct()]);

    render(await EditProductPage({ params: Promise.resolve({ id: 'tente-tunnel' }) }));

    expect(await screen.findByLabelText('Nom')).toHaveValue('Tente Tunnel');
    expect(calls[0].path).toBe('/bff/products/tente-tunnel');
    expect(screen.getByRole('heading', { level: 1, name: 'Modifier le produit' })).toBeInTheDocument();
  });
});

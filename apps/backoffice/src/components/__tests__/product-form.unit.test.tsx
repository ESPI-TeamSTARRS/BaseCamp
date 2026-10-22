// @vitest-environment jsdom
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ProductForm } from '../product-form';
import { makeProduct, stubApi } from './stub-api';

afterEach(() => {
  vi.unstubAllGlobals();
});

async function fillCreateForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Nom'), 'Réchaud compact');
  await user.selectOptions(screen.getByLabelText('Catégorie'), 'cuisine');
  await user.type(screen.getByLabelText('Prix (€)'), '39,9');
  await user.type(screen.getByLabelText('Stock'), '25');
  await user.type(screen.getByLabelText('Description courte'), 'Léger et fiable');
  await user.type(screen.getByLabelText('Description'), 'Un réchaud pour la randonnée.');
}

describe('ProductForm – création', () => {
  it('affiche tous les champs avec leur libellé', () => {
    render(<ProductForm />);

    for (const label of [
      'Nom',
      'Identifiant (facultatif)',
      'Catégorie',
      'Prix (€)',
      'Prix barré (€, facultatif)',
      'Stock',
      'Description courte',
      'Description',
      'Poids (g)',
      'Matériau',
    ]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
    expect(screen.getByRole('button', { name: 'Créer le produit' })).toBeEnabled();
  });

  it('refuse une saisie invalide côté client, sans appeler l’API, et place le focus sur le premier champ en erreur', async () => {
    const calls = stubApi(() => [201, makeProduct()]);
    const user = userEvent.setup();
    render(<ProductForm />);

    await user.click(screen.getByRole('button', { name: 'Créer le produit' }));

    expect(calls).toEqual([]);
    expect(screen.getByRole('alert')).toHaveTextContent('Corrigez 6 champs avant d’enregistrer.');
    expect(screen.getByText('Le nom est obligatoire.')).toBeInTheDocument();
    expect(screen.getByLabelText('Nom')).toHaveFocus();
    expect(screen.getByLabelText('Nom')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('Nom')).toHaveAccessibleDescription('Le nom est obligatoire.');
  });

  it('signale un prix à plus de deux décimales et un stock non entier', async () => {
    stubApi(() => [201, makeProduct()]);
    const user = userEvent.setup();
    render(<ProductForm />);
    await fillCreateForm(user);

    await user.clear(screen.getByLabelText('Prix (€)'));
    await user.type(screen.getByLabelText('Prix (€)'), '12,345');
    await user.clear(screen.getByLabelText('Stock'));
    await user.type(screen.getByLabelText('Stock'), '2.5');
    await user.click(screen.getByRole('button', { name: 'Créer le produit' }));

    expect(screen.getByText(/Prix invalide/)).toBeInTheDocument();
    expect(screen.getByText(/Stock : nombre entier/)).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Corrigez 2 champs');
  });

  it('crée le produit avec des prix en centimes puis propose d’ajouter des images', async () => {
    const calls = stubApi(() => [201, makeProduct({ id: 'rechaud-compact', name: 'Réchaud compact' })]);
    const user = userEvent.setup();
    render(<ProductForm />);
    await fillCreateForm(user);
    await user.type(screen.getByLabelText('Poids (g)'), '350');

    await user.click(screen.getByRole('button', { name: 'Créer le produit' }));

    expect(await screen.findByText('Produit « Réchaud compact » créé.')).toBeInTheDocument();
    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({
      method: 'POST',
      path: '/bff/products',
      body: {
        name: 'Réchaud compact',
        category: 'cuisine',
        price_cents: 3990,
        compare_at_price_cents: null,
        stock: 25,
        specs: { weight_grams: 350 },
      },
    });
    expect(screen.getByRole('link', { name: 'Ajouter des images' })).toHaveAttribute(
      'href',
      '/produits/rechaud-compact'
    );
  });

  it('place l’erreur « existe déjà » sur l’identifiant', async () => {
    stubApi(() => [409, { detail: 'Un produit portant cet identifiant existe déjà.', code: 'duplicate' }]);
    const user = userEvent.setup();
    render(<ProductForm />);
    await fillCreateForm(user);

    await user.click(screen.getByRole('button', { name: 'Créer le produit' }));

    expect(await screen.findByText('Un produit portant cet identifiant existe déjà.')).toBeInTheDocument();
    expect(screen.getByLabelText('Identifiant (facultatif)')).toHaveAttribute('aria-invalid', 'true');
  });

  it('affiche une erreur serveur dans une alerte et garde la saisie', async () => {
    stubApi(() => [
      503,
      {
        detail: 'Le catalogue est momentanément indisponible. Réessayez dans un instant.',
        code: 'unavailable',
      },
    ]);
    const user = userEvent.setup();
    render(<ProductForm />);
    await fillCreateForm(user);

    await user.click(screen.getByRole('button', { name: 'Créer le produit' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('momentanément indisponible');
    expect(screen.getByLabelText('Nom')).toHaveValue('Réchaud compact');
  });
});

describe('ProductForm – modification', () => {
  const PRODUCT = makeProduct();

  it('charge le produit, puis affiche le formulaire prérempli', async () => {
    stubApi(() => [200, PRODUCT]);

    render(<ProductForm productId="tente-tunnel" />);

    expect(screen.getByRole('status')).toHaveTextContent('Chargement du produit…');
    expect(await screen.findByLabelText('Nom')).toHaveValue('Tente Tunnel');
    expect(screen.getByLabelText('Prix (€)')).toHaveValue('129,90');
    expect(screen.getByLabelText('Poids (g)')).toHaveValue('2100');
    expect(screen.getByLabelText('Catégorie')).toHaveValue('tentes');
    expect(screen.queryByLabelText('Identifiant (facultatif)')).not.toBeInTheDocument();
  });

  it('indique un produit introuvable avec un retour au catalogue', async () => {
    stubApi(() => [404, { detail: 'Produit introuvable.', code: 'not_found' }]);

    render(<ProductForm productId="nope" />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Produit introuvable.');
    expect(screen.getByRole('link', { name: 'Retour au catalogue' })).toHaveAttribute('href', '/produits');
  });
  it('recharge après une panne de chargement quand l’API revient', async () => {
    let up = false;
    stubApi(() =>
      up ? [200, PRODUCT] : [502, { detail: 'Une erreur est survenue. Réessayez.', code: 'error' }]
    );
    const user = userEvent.setup();
    render(<ProductForm productId="tente-tunnel" />);
    const alert = await screen.findByRole('alert');
    up = true;

    await user.click(within(alert).getByRole('button', { name: 'Réessayer' }));

    expect(await screen.findByLabelText('Nom')).toHaveValue('Tente Tunnel');
  });

  it('enregistre avec la version lue, convertit les prix en centimes et passe à la version suivante', async () => {
    const saved = makeProduct({ price_cents: 11990, stock: 7, version: 4 });
    const calls = stubApi((call) => (call.method === 'PATCH' ? [200, saved] : [200, PRODUCT]));
    const user = userEvent.setup();
    render(<ProductForm productId="tente-tunnel" />);
    await screen.findByLabelText('Nom');

    await user.clear(screen.getByLabelText('Prix (€)'));
    await user.type(screen.getByLabelText('Prix (€)'), '119,90');
    await user.clear(screen.getByLabelText('Stock'));
    await user.type(screen.getByLabelText('Stock'), '7');
    await user.click(screen.getByRole('button', { name: 'Enregistrer les modifications' }));

    expect(await screen.findByText('Modifications enregistrées.')).toBeInTheDocument();
    const patch = calls.find((c) => c.method === 'PATCH');
    expect(patch).toMatchObject({
      path: '/bff/products/tente-tunnel',
      body: { version: 3, price_cents: 11990, stock: 7 },
    });
    expect(screen.getByLabelText('Prix (€)')).toHaveValue('119,90');
  });

  it('en cas de conflit de version : message clair, saisie conservée, puis rechargement sur demande', async () => {
    const latest = makeProduct({ name: 'Tente Tunnel 2', version: 5 });
    let conflict = true;
    stubApi((call) => {
      if (call.method === 'PATCH')
        return [409, { detail: 'Ce produit a été modifié ailleurs.', code: 'stale_version' }];
      return [200, conflict ? PRODUCT : latest];
    });
    const user = userEvent.setup();
    render(<ProductForm productId="tente-tunnel" />);
    await screen.findByLabelText('Nom');
    await user.clear(screen.getByLabelText('Stock'));
    await user.type(screen.getByLabelText('Stock'), '1');

    await user.click(screen.getByRole('button', { name: 'Enregistrer les modifications' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Ce produit a été modifié ailleurs depuis son ouverture');
    expect(screen.getByLabelText('Stock')).toHaveValue('1');
    conflict = false;
    await user.click(within(alert).getByRole('button', { name: 'Recharger la dernière version' }));

    await waitFor(() => expect(screen.getByLabelText('Nom')).toHaveValue('Tente Tunnel 2'));
    expect(screen.getByLabelText('Stock')).toHaveValue('12');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('un produit archivé est en lecture seule', async () => {
    stubApi(() => [200, makeProduct({ archived_at: '2026-10-01T00:00:00Z', image_urls: ['/media/a.png'] })]);

    render(<ProductForm productId="tente-tunnel" />);

    expect(await screen.findByText(/Ce produit est archivé/)).toBeInTheDocument();
    expect(screen.getByLabelText('Nom')).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Enregistrer les modifications' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Archiver ce produit' })).not.toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Image 1 de Tente Tunnel' })).toBeInTheDocument();
  });

  it('archive après confirmation : le produit passe en lecture seule', async () => {
    const archived = makeProduct({ archived_at: '2026-10-22T00:00:00Z', version: 4 });
    const calls = stubApi((call) => (call.path.endsWith('/archive') ? [200, archived] : [200, PRODUCT]));
    const user = userEvent.setup();
    render(<ProductForm productId="tente-tunnel" />);
    await screen.findByLabelText('Nom');

    await user.click(screen.getByRole('button', { name: 'Archiver ce produit' }));
    expect(calls.some((c) => c.path.endsWith('/archive'))).toBe(false);
    await user.click(screen.getByRole('button', { name: 'Confirmer l’archivage' }));

    expect(await screen.findByText('Produit archivé.')).toBeInTheDocument();
    expect(screen.getByLabelText('Nom')).toBeDisabled();
  });
});

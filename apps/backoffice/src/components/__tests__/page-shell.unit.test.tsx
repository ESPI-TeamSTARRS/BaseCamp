// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PageShell } from '../page-shell';

describe('PageShell', () => {
  it('donne un titre, une navigation et une déconnexion en POST', () => {
    render(
      <PageShell title="Catalogue">
        <p>contenu</p>
      </PageShell>
    );

    expect(screen.getByRole('heading', { level: 1, name: 'Catalogue' })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Navigation principale' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Catalogue' })).toHaveAttribute('href', '/produits');
    const logout = screen.getByRole('button', { name: 'Se déconnecter' });
    expect(logout.closest('form')).toHaveAttribute('action', '/session/logout');
    expect(logout.closest('form')).toHaveAttribute('method', 'post');
    expect(screen.getByRole('main')).toHaveTextContent('contenu');
  });
});

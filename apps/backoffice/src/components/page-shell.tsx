import Link from 'next/link';
import type { ReactNode } from 'react';

/** Cadre commun des ecrans proteges : navigation, deconnexion, titre de page. */
export function PageShell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <>
      <header className="shell-header">
        <strong>Basecamp · Back-office</strong>
        <nav aria-label="Navigation principale">
          <Link href="/produits">Catalogue</Link>
          <Link href="/commandes">Commandes</Link>
          <form method="post" action="/session/logout">
            <button type="submit" className="link-button">
              Se déconnecter
            </button>
          </form>
        </nav>
      </header>
      <main className="page">
        <h1>{title}</h1>
        {children}
      </main>
    </>
  );
}

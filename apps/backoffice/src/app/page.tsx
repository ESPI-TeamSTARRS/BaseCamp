import Link from 'next/link';
import { PageShell } from '@/components/page-shell';

export default function HomePage() {
  return (
    <PageShell title="Back-office Basecamp">
      <p>Espace réservé à l’équipe.</p>
      <p>
        <Link className="button" href="/produits">
          Gérer le catalogue
        </Link>{' '}
        <Link className="button" href="/commandes">
          Consulter les commandes
        </Link>
      </p>
    </PageShell>
  );
}

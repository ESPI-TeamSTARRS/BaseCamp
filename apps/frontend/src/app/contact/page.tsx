import { ContentPage, ContentSection } from '../../components/ContentPage';
import { publisher } from '../../lib/legal-info';

export const metadata = {
  title: 'Contact',
  description:
    'Une question sur votre commande ou notre matériel de bivouac ? Contactez Basecamp Outdoor par email, réponse garantie sous 24h ouvrées du lundi au vendredi.',
  alternates: { canonical: '/contact' },
  robots: { index: true, follow: true },
};

export default function ContactPage() {
  return (
    <ContentPage title="Contact" narrow>
      <ContentSection title="Nous écrire">
        <p>
          Une question sur votre commande ou notre matériel ? Écrivez-nous à{' '}
          <a href={`mailto:${publisher.email}`} className="text-forest underline">
            {publisher.email}
          </a>{' '}
          — réponse sous 24h ouvrées, du lundi au vendredi.
        </p>
      </ContentSection>
      <ContentSection title="Notre adresse">
        <p>
          {publisher.name}
          <br />
          {publisher.address}
        </p>
        <p>Il n&apos;y a pas d&apos;accueil du public : le service client répond uniquement par courriel.</p>
      </ContentSection>
      <ContentSection title="Une commande en cours ?">
        <p>
          Retrouvez son état sur la page{' '}
          <a href="/suivi" className="text-forest underline">
            Suivre ma commande
          </a>{' '}
          avec son numéro et votre courriel.
        </p>
      </ContentSection>
    </ContentPage>
  );
}

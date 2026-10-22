import { ContentPage, ContentSection } from '../../components/ContentPage';
import { legalUpdatedAt, publisher } from '../../lib/legal-info';

export const metadata = {
  title: 'Mentions Légales',
  description:
    'Mentions légales de Basecamp Outdoor : raison sociale, forme juridique, siège social, SIRET, directeur de la publication et coordonnées de notre hébergeur web.',
  alternates: { canonical: '/mentions-legales' },
  robots: { index: true, follow: true },
};

export default function MentionsLegalesPage() {
  return (
    <ContentPage title="Mentions Légales" updatedAt={legalUpdatedAt}>
      <ContentSection title="Éditeur du site">
        <p>
          Le site basecamp-outdoor.fr est édité par {publisher.name}, {publisher.form.toLowerCase()} au
          capital de {publisher.capital}, dont le siège social est situé {publisher.address}.
        </p>
        <ul className="list-disc space-y-1 pl-5">
          <li>{publisher.rcs}</li>
          <li>SIRET : {publisher.siret}</li>
          <li>TVA intracommunautaire : {publisher.vat}</li>
          <li>
            Courriel :{' '}
            <a href={`mailto:${publisher.email}`} className="text-forest underline">
              {publisher.email}
            </a>
          </li>
        </ul>
      </ContentSection>
      <ContentSection title="Directeur de la publication">
        <p>Le directeur de la publication est {publisher.director}, en qualité de président de la société.</p>
      </ContentSection>
      <ContentSection title="Hébergement">
        <p>
          Le site est hébergé sur l&apos;{publisher.host}. Aucun hébergeur commercial n&apos;intervient dans
          ce projet.
        </p>
      </ContentSection>
      <ContentSection title="Propriété intellectuelle">
        <p>
          Les textes, images, logos et éléments graphiques du site sont la propriété de {publisher.name} ou de
          ses partenaires. Toute reproduction, même partielle, sans autorisation écrite préalable est
          interdite.
        </p>
      </ContentSection>
      <ContentSection title="Responsabilité">
        <p>
          L&apos;éditeur s&apos;efforce de fournir des informations exactes et à jour, sans pouvoir garantir
          l&apos;absence d&apos;erreur ou d&apos;interruption du service. Les liens vers des sites tiers
          n&apos;engagent pas sa responsabilité.
        </p>
      </ContentSection>
      <ContentSection title="Contact">
        <p>
          Pour toute question, écrivez à {publisher.email} ou consultez la page{' '}
          <a href="/contact" className="text-forest underline">
            Contact
          </a>
          .
        </p>
      </ContentSection>
    </ContentPage>
  );
}

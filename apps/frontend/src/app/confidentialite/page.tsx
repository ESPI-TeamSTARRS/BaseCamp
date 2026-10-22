import { ContentPage, ContentSection } from '../../components/ContentPage';
import { legalUpdatedAt, publisher } from '../../lib/legal-info';

export const metadata = {
  title: 'Politique de Confidentialité',
  description:
    'Politique de confidentialité Basecamp Outdoor : données collectées, finalités, durée de conservation et exercice de vos droits RGPD auprès de notre équipe.',
  alternates: { canonical: '/confidentialite' },
  robots: { index: true, follow: true },
};

export default function ConfidentialitePage() {
  return (
    <ContentPage title="Politique de Confidentialité" updatedAt={legalUpdatedAt}>
      <ContentSection title="Responsable du traitement">
        <p>
          Le responsable du traitement de vos données personnelles est {publisher.name}, {publisher.address}.
          Contact : {publisher.email}.
        </p>
      </ContentSection>
      <ContentSection title="Données collectées">
        <ul className="list-disc space-y-1 pl-5">
          <li>
            Compte : adresse courriel et mot de passe (conservé uniquement sous forme chiffrée irréversible).
          </li>
          <li>Commande : nom, adresse de livraison, courriel, contenu et montant de la commande.</li>
          <li>Paiement : aucune donnée bancaire réelle n&apos;est collectée ; le paiement est simulé.</li>
          <li>
            Technique : journaux de fonctionnement (identifiant de corrélation, adresse courriel
            pseudonymisée).
          </li>
        </ul>
      </ContentSection>
      <ContentSection title="Finalités et bases légales">
        <ul className="list-disc space-y-1 pl-5">
          <li>Gérer votre compte et vos commandes : exécution du contrat.</li>
          <li>Vous envoyer les courriels liés à votre commande ou à votre compte : exécution du contrat.</li>
          <li>Assurer la sécurité et le bon fonctionnement du service : intérêt légitime.</li>
          <li>Respecter nos obligations comptables et légales : obligation légale.</li>
        </ul>
      </ContentSection>
      <ContentSection title="Durées de conservation">
        <ul className="list-disc space-y-1 pl-5">
          <li>Compte : jusqu&apos;à sa suppression, puis effacement ou anonymisation.</li>
          <li>Commandes et factures : 10 ans, conformément aux obligations comptables.</li>
          <li>Journaux techniques : 12 mois au plus.</li>
        </ul>
      </ContentSection>
      <ContentSection title="Destinataires">
        <p>
          Vos données sont réservées à l&apos;équipe de {publisher.name} et à ses sous-traitants strictement
          nécessaires (hébergement, envoi de courriels). Elles ne sont ni vendues ni cédées à des fins
          commerciales.
        </p>
      </ContentSection>
      <ContentSection title="Vos droits">
        <p>
          Vous disposez des droits d&apos;accès, de rectification, d&apos;effacement, de limitation,
          d&apos;opposition et de portabilité. Pour les exercer, écrivez à {publisher.email} ; une réponse
          vous est apportée sous un mois. En cas de désaccord, vous pouvez saisir la CNIL (cnil.fr).
        </p>
      </ContentSection>
      <ContentSection title="Cookies et stockage local">
        <p>
          Le site utilise uniquement le stockage nécessaire à son fonctionnement (panier, session de
          connexion). Aucun traceur publicitaire ni de mesure d&apos;audience tiers n&apos;est déposé.
        </p>
      </ContentSection>
      <ContentSection title="Sécurité">
        <p>
          Les échanges sont protégés, les mots de passe sont chiffrés de façon irréversible et l&apos;accès
          aux données est limité aux personnes habilitées.
        </p>
      </ContentSection>
    </ContentPage>
  );
}

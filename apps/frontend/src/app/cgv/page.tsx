import { ContentPage, ContentSection } from '../../components/ContentPage';
import { legalUpdatedAt, publisher } from '../../lib/legal-info';

export const metadata = {
  title: 'Conditions Générales de Vente',
  description:
    'Conditions générales de vente Basecamp Outdoor : commande, prix, livraison 24/48h, droit de rétractation, retours gratuits 30 jours et garanties.',
  alternates: { canonical: '/cgv' },
  robots: { index: true, follow: true },
};

export default function CgvPage() {
  return (
    <ContentPage title="Conditions Générales de Vente" updatedAt={legalUpdatedAt}>
      <ContentSection title="1. Objet et vendeur">
        <p>
          Les présentes conditions régissent les ventes conclues sur basecamp-outdoor.fr entre{' '}
          {publisher.name} ({publisher.address}) et toute personne passant commande. Passer commande vaut
          acceptation de ces conditions.
        </p>
      </ContentSection>
      <ContentSection title="2. Produits et prix">
        <p>
          Les produits sont décrits avec la plus grande exactitude possible. Les prix sont indiqués en euros,
          toutes taxes comprises, hors frais éventuels précisés avant validation. Le montant est recalculé au
          moment de la commande ; le prix applicable est celui affiché lors de la validation.
        </p>
      </ContentSection>
      <ContentSection title="3. Commande">
        <p>
          La commande est ferme après validation du récapitulatif et confirmation du paiement. Un courriel de
          confirmation est envoyé. Le vendeur peut refuser ou annuler une commande en cas de rupture de stock
          ou de paiement refusé ; le client en est informé et, le cas échéant, remboursé.
        </p>
      </ContentSection>
      <ContentSection title="4. Paiement">
        <p>
          Le paiement est exigible à la commande. Dans le cadre de ce projet pédagogique, le service de
          paiement est simulé : aucune donnée bancaire réelle ne doit être saisie et aucun débit n&apos;est
          effectué.
        </p>
      </ContentSection>
      <ContentSection title="5. Livraison">
        <p>
          Les commandes sont expédiées sous 24 à 48 heures ouvrées après confirmation du paiement, à
          l&apos;adresse indiquée par le client. Le suivi d&apos;une commande est disponible sur la page{' '}
          <a href="/suivi" className="text-forest underline">
            Suivre ma commande
          </a>
          .
        </p>
      </ContentSection>
      <ContentSection title="6. Droit de rétractation">
        <p>
          Conformément au code de la consommation, le consommateur dispose de 14 jours à compter de la
          réception pour se rétracter, sans avoir à motiver sa décision. Il notifie sa demande à{' '}
          {publisher.email}. Le remboursement intervient au plus tard 14 jours après la notification, dès
          réception du produit retourné.
        </p>
      </ContentSection>
      <ContentSection title="7. Retours">
        <p>
          Au-delà du droit légal, Basecamp Outdoor accorde 30 jours pour retourner un produit non utilisé,
          dans son emballage d&apos;origine. Les frais de retour sont à la charge du vendeur.
        </p>
      </ContentSection>
      <ContentSection title="8. Garanties">
        <p>
          Le vendeur répond de la garantie légale de conformité (2 ans à compter de la délivrance du bien) et
          de la garantie légale des vices cachés, selon les articles L.217-3 et suivants du code de la
          consommation et 1641 et suivants du code civil. Ces garanties s&apos;appliquent sans frais pour le
          client.
        </p>
      </ContentSection>
      <ContentSection title="9. Responsabilité">
        <p>
          Le vendeur n&apos;est pas responsable des dommages résultant d&apos;un usage non conforme du
          matériel ou d&apos;un cas de force majeure. Les conseils d&apos;usage restent indicatifs :
          l&apos;activité de plein air comporte des risques propres.
        </p>
      </ContentSection>
      <ContentSection title="10. Données personnelles">
        <p>
          Le traitement de vos données est décrit dans la{' '}
          <a href="/confidentialite" className="text-forest underline">
            politique de confidentialité
          </a>
          .
        </p>
      </ContentSection>
      <ContentSection title="11. Médiation et litiges">
        <p>
          En cas de litige, le client peut contacter le service client à {publisher.email}. À défaut de
          solution amiable, il peut recourir gratuitement à un médiateur de la consommation (liste sur
          economie.gouv.fr/mediation-conso) ou à la plateforme européenne de règlement en ligne des litiges.
          Le droit français est applicable ; à défaut d&apos;accord, les tribunaux compétents sont ceux du
          domicile du consommateur.
        </p>
      </ContentSection>
    </ContentPage>
  );
}

import { ContentPage } from '../../components/ContentPage';
import { OrderLookupForm } from '../../components/OrderLookupForm';

export const metadata = {
  title: 'Suivre ma commande',
  description:
    'Suivez votre commande Basecamp Outdoor : saisissez votre numéro de commande et l’email utilisé pour connaître son état, ses articles et son total.',
  alternates: { canonical: '/suivi' },
  robots: { index: true, follow: true },
};

export default function SuiviPage() {
  return (
    <ContentPage title="Suivre ma commande" narrow>
      <p>
        Retrouvez l&apos;état de votre commande avec son numéro (BC-…) et l&apos;email utilisé au moment de la
        commande. Besoin d&apos;aide ?{' '}
        <a href="/contact" className="text-forest underline">
          Contactez notre service client
        </a>
        .
      </p>
      <OrderLookupForm />
    </ContentPage>
  );
}

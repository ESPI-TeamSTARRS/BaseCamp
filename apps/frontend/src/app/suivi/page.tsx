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
    <section className="mx-auto max-w-xl px-4 py-16">
      <h1 className="mb-4 text-3xl font-bold text-granite">Suivre ma commande</h1>
      <p className="text-granite/70">
        Retrouvez l&apos;état de votre commande avec son numéro (BC-…) et l&apos;email utilisé au moment de la
        commande. Besoin d&apos;aide ? Contactez notre service client.
      </p>
      <OrderLookupForm />
    </section>
  );
}

export const metadata = {
  title: 'Suivre ma commande',
  description:
    'Suivez votre commande Basecamp Outdoor en temps réel : lien de suivi envoyé par email dès expédition sous 24/48h après achat, avec support client dédié.',
  alternates: { canonical: '/suivi' },
  robots: { index: true, follow: true },
};

export default function SuiviPage() {
  return (
    <section className="mx-auto max-w-xl px-4 py-16">
      <h1 className="mb-4 text-3xl font-bold text-granite">Suivre ma commande</h1>
      <p className="text-granite/70">
        Le lien de suivi de votre colis vous est envoyé par email dès l&apos;expédition (sous 24/48h après
        votre commande). Besoin d&apos;aide ? Contactez notre service client.
      </p>
    </section>
  );
}

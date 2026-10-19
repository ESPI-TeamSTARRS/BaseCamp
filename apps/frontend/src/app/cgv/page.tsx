export const metadata = {
  title: 'Conditions Générales de Vente',
  description:
    'Conditions générales de vente Basecamp Outdoor : commande, prix, livraison 24/48h, droit de rétractation, retours gratuits 30 jours et garanties.',
  alternates: { canonical: '/cgv' },
  robots: { index: true, follow: true },
};

export default function CgvPage() {
  return (
    <section className="mx-auto max-w-2xl px-4 py-16">
      <h1 className="mb-4 text-3xl font-bold text-granite">Conditions Générales de Vente</h1>
      <p className="text-granite/70">
        Contenu à finaliser avec votre conseil juridique avant mise en production : modalités de commande,
        prix, livraison (24/48h), droit de rétractation et retours (30 jours), garanties légales.
      </p>
    </section>
  );
}

export const metadata = {
  title: 'Mentions Légales',
  description:
    'Mentions légales de Basecamp Outdoor : raison sociale, forme juridique, siège social, SIRET, directeur de la publication et coordonnées de notre hébergeur web.',
  alternates: { canonical: '/mentions-legales' },
  robots: { index: true, follow: true },
};

export default function MentionsLegalesPage() {
  return (
    <section className="mx-auto max-w-2xl px-4 py-16">
      <h1 className="mb-4 text-3xl font-bold text-granite">Mentions Légales</h1>
      <p className="text-granite/70">
        Contenu à finaliser : raison sociale, forme juridique, siège social, SIRET, directeur de la
        publication, hébergeur.
      </p>
    </section>
  );
}

export const metadata = {
  title: 'Politique de Confidentialité',
  description:
    'Politique de confidentialité Basecamp Outdoor : données collectées, finalités, durée de conservation et exercice de vos droits RGPD auprès de notre équipe.',
  alternates: { canonical: '/confidentialite' },
  robots: { index: true, follow: true },
};

export default function ConfidentialitePage() {
  return (
    <section className="mx-auto max-w-2xl px-4 py-16">
      <h1 className="mb-4 text-3xl font-bold text-granite">Politique de Confidentialité</h1>
      <p className="text-granite/70">
        Contenu à finaliser avec votre conseil juridique avant mise en production : données collectées,
        finalités, durée de conservation, droits RGPD et coordonnées du délégué à la protection des données.
      </p>
    </section>
  );
}

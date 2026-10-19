export const metadata = {
  title: 'Contact',
  description:
    "Une question sur votre commande ou notre matériel de bivouac ? Contactez Basecamp Outdoor par email, réponse garantie sous 24h ouvrées du lundi au vendredi.",
  alternates: { canonical: '/contact' },
  robots: { index: true, follow: true },
};

export default function ContactPage() {
  return (
    <section className="mx-auto max-w-xl px-4 py-16">
      <h1 className="mb-4 text-3xl font-bold text-granite">Contact</h1>
      <p className="text-granite/70">
        Une question sur votre commande ou notre matériel ? Écrivez-nous à{' '}
        <a href="mailto:contact@basecamp-outdoor.fr" className="text-forest underline">
          contact@basecamp-outdoor.fr
        </a>{' '}
        — réponse sous 24h ouvrées.
      </p>
    </section>
  );
}

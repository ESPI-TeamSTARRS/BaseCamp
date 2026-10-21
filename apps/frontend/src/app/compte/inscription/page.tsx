import { RegistrationForm } from '../../../components/RegistrationForm';

export const metadata = {
  title: 'Créer mon compte',
  description:
    'Créez votre compte Basecamp Outdoor pour suivre vos commandes de matériel de bivouac et de randonnée.',
  alternates: { canonical: '/compte/inscription' },
  robots: { index: false, follow: true },
};

export default function RegistrationPage() {
  return (
    <section className="mx-auto max-w-md px-4 py-12">
      <h1 className="mb-2 text-3xl font-bold text-forest-deep">Créer mon compte</h1>
      <p className="mb-6 text-granite/70">
        Quelques secondes pour suivre vos commandes et préparer votre prochain bivouac.
      </p>
      <RegistrationForm />
    </section>
  );
}

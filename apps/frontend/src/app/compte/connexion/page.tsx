import { LoginForm } from '../../../components/LoginForm';

export const metadata = {
  title: 'Me connecter',
  description: 'Connectez-vous à votre compte Basecamp Outdoor pour suivre vos commandes de matériel.',
  alternates: { canonical: '/compte/connexion' },
  robots: { index: false, follow: true },
};

export default function LoginPage() {
  return (
    <section className="mx-auto max-w-md px-4 py-12">
      <h1 className="mb-2 text-3xl font-bold text-forest-deep">Me connecter</h1>
      <p className="mb-6 text-granite/70">Retrouvez vos commandes et votre matériel favori.</p>
      <LoginForm />
    </section>
  );
}

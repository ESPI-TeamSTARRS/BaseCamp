import { ForgotPasswordForm } from '../../../components/ForgotPasswordForm';

export const metadata = {
  title: 'Mot de passe oublié',
  description: 'Recevez par email un lien pour choisir un nouveau mot de passe Basecamp Outdoor.',
  alternates: { canonical: '/compte/mot-de-passe-oublie' },
  robots: { index: false, follow: true },
};

export default function ForgotPasswordPage() {
  return (
    <section className="mx-auto max-w-md px-4 py-12">
      <h1 className="mb-2 text-3xl font-bold text-forest-deep">Mot de passe oublié</h1>
      <p className="mb-6 text-granite/70">
        Saisissez l&apos;adresse de votre compte : si elle existe, vous recevrez un lien valable 30 minutes.
      </p>
      <ForgotPasswordForm />
    </section>
  );
}

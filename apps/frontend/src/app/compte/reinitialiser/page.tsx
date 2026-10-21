import { ResetPasswordForm } from '../../../components/ResetPasswordForm';

export const metadata = {
  title: 'Nouveau mot de passe',
  robots: { index: false, follow: false },
  referrer: 'no-referrer',
};

export default function ResetPasswordPage() {
  return (
    <section className="mx-auto max-w-md px-4 py-12">
      <h1 className="mb-6 text-3xl font-bold text-forest-deep">Choisir un nouveau mot de passe</h1>
      <ResetPasswordForm />
    </section>
  );
}

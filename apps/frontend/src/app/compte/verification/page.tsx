import { EmailVerification } from '../../../components/EmailVerification';

export const metadata = {
  title: "Confirmation de l'adresse email",
  robots: { index: false, follow: false },
  referrer: 'no-referrer',
};

export default function EmailVerificationPage() {
  return (
    <section className="mx-auto max-w-md px-4 py-12">
      <h1 className="mb-6 text-3xl font-bold text-forest-deep">Confirmation de l&apos;adresse email</h1>
      <EmailVerification />
    </section>
  );
}

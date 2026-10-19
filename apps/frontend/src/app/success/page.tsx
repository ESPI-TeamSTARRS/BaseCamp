import Link from 'next/link';
import { CheckCircle2 } from 'lucide-react';

export const metadata = {
  robots: { index: false, follow: false },
};

export default function SuccessPage() {
  return (
    <section className="mx-auto flex max-w-xl flex-col items-center gap-4 px-4 py-24 text-center">
      <CheckCircle2 size={56} className="text-forest" />
      <h1 className="text-2xl font-bold text-granite">Merci pour votre commande !</h1>
      <p className="text-granite/70">
        Votre paiement a bien été reçu. Un email de confirmation vous a été envoyé, et vous recevrez un suivi
        d&apos;expédition dès que votre colis partira (généralement sous 24/48h).
      </p>
      <Link
        href="/"
        className="mt-4 rounded-full bg-forest px-6 py-3 text-sm font-semibold text-sand hover:bg-forest-light"
      >
        Retour à la boutique
      </Link>
    </section>
  );
}

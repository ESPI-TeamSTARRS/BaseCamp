import Link from 'next/link';
import { CheckCircle2 } from 'lucide-react';
import { OrderRecap } from '@/components/OrderRecap';

export const metadata = {
  robots: { index: false, follow: false },
};

const ORDER_NUMBER = /^BC-[A-Z0-9]{10}$/;

interface Props {
  searchParams: Promise<{ commande?: string | string[] }>;
}

export default async function SuccessPage({ searchParams }: Props) {
  const { commande } = await searchParams;
  // Le numéro n'est affiché que s'il a exactement le format d'un numéro de commande.
  const number = typeof commande === 'string' && ORDER_NUMBER.test(commande) ? commande : null;
  return (
    <section className="mx-auto flex max-w-xl flex-col items-center gap-4 px-4 py-24 text-center">
      <CheckCircle2 size={56} className="text-forest" />
      <h1 className="text-2xl font-bold text-granite">Merci pour votre commande !</h1>
      {number && (
        <p className="text-granite/70">
          Numéro de commande : <strong className="text-granite">{number}</strong>
        </p>
      )}
      {number && <OrderRecap number={number} />}
      <p className="text-granite/70">
        Votre paiement de démonstration a bien été enregistré. Conservez votre numéro de commande et votre
        email pour suivre son état.
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

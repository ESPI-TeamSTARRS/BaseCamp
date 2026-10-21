import { MyOrders } from '../../../components/MyOrders';

export const metadata = {
  title: 'Mes commandes',
  description: 'Retrouvez les commandes de votre compte Basecamp Outdoor, sans numéro ni email.',
  alternates: { canonical: '/compte/commandes' },
  robots: { index: false, follow: false },
};

export default function MyOrdersPage() {
  return (
    <section className="mx-auto max-w-2xl px-4 py-12">
      <h1 className="mb-2 text-3xl font-bold text-forest-deep">Mes commandes</h1>
      <p className="mb-6 text-granite/70">Toutes les commandes passées avec votre compte.</p>
      <MyOrders />
    </section>
  );
}

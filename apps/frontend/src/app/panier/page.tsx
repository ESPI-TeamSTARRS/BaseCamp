import type { Metadata } from 'next';
import { CartPage } from '../../components/CartPage';

export const metadata: Metadata = {
  title: 'Panier',
  robots: { index: false, follow: false },
};

export default function PanierPage() {
  return <CartPage />;
}

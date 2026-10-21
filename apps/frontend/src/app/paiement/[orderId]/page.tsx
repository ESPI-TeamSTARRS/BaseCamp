import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { PaymentScreen } from '../../../components/PaymentScreen';
import { isOrderId } from '../../../lib/order-payment';

export const metadata: Metadata = {
  title: 'Paiement',
  robots: { index: false, follow: false },
};

interface Props {
  params: Promise<{ orderId: string }>;
}

export default async function PaiementPage({ params }: Props) {
  const { orderId } = await params;
  if (!isOrderId(orderId)) notFound();
  return <PaymentScreen orderId={orderId} />;
}

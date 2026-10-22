import { OrderDetailView } from '@/components/order-detail';
import { PageShell } from '@/components/page-shell';

export default async function OrderDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <PageShell title="Détail de la commande">
      <OrderDetailView orderId={id} />
    </PageShell>
  );
}

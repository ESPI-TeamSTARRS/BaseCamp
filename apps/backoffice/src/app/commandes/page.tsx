import { OrderList } from '@/components/order-list';
import { PageShell } from '@/components/page-shell';

export default function OrdersPage() {
  return (
    <PageShell title="Commandes">
      <OrderList />
    </PageShell>
  );
}

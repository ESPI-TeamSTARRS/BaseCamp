import { PageShell } from '@/components/page-shell';
import { ProductList } from '@/components/product-list';

export default function ProductsPage() {
  return (
    <PageShell title="Catalogue">
      <ProductList />
    </PageShell>
  );
}

import { PageShell } from '@/components/page-shell';
import { ProductForm } from '@/components/product-form';

export default function NewProductPage() {
  return (
    <PageShell title="Nouveau produit">
      <ProductForm />
    </PageShell>
  );
}

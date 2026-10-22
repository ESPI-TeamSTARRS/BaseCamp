import { PageShell } from '@/components/page-shell';
import { ProductForm } from '@/components/product-form';

export default async function EditProductPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <PageShell title="Modifier le produit">
      <ProductForm productId={id} />
    </PageShell>
  );
}

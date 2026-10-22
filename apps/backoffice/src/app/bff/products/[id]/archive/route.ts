import { handleCatalog } from '@/lib/handlers/catalog-handlers';
import { runtime } from '@/lib/runtime';

export const dynamic = 'force-dynamic';

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  return handleCatalog(request, 'archive', (await params).id, runtime());
}

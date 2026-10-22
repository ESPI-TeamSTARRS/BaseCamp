import { handleCatalog } from '@/lib/handlers/catalog-handlers';
import { runtime } from '@/lib/runtime';

export const dynamic = 'force-dynamic';

type Context = { params: Promise<{ id: string }> };

export async function GET(request: Request, { params }: Context) {
  return handleCatalog(request, 'get', (await params).id, runtime());
}

export async function PATCH(request: Request, { params }: Context) {
  return handleCatalog(request, 'update', (await params).id, runtime());
}

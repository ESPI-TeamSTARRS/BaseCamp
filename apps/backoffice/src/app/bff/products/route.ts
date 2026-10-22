import { handleCatalog } from '@/lib/handlers/catalog-handlers';
import { runtime } from '@/lib/runtime';

export const dynamic = 'force-dynamic';

export function GET(request: Request) {
  return handleCatalog(request, 'list', undefined, runtime());
}

export function POST(request: Request) {
  return handleCatalog(request, 'create', undefined, runtime());
}

import { handleOrders } from '@/lib/handlers/order-handlers';
import { runtime } from '@/lib/runtime';

export const dynamic = 'force-dynamic';

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  return handleOrders(request, 'get', (await params).id, runtime());
}

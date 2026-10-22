import { handleOrders } from '@/lib/handlers/order-handlers';
import { runtime } from '@/lib/runtime';

export const dynamic = 'force-dynamic';

export function GET(request: Request) {
  return handleOrders(request, 'list', undefined, runtime());
}

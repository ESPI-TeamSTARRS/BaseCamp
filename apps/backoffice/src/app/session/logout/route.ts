import { handleLogout } from '@/lib/handlers/logout-handler';

export const dynamic = 'force-dynamic';

export function POST(request: Request) {
  return handleLogout(request);
}

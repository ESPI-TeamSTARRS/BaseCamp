import { handleIdentify } from '@/lib/handlers/login-steps';
import { runtime } from '@/lib/runtime';

export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  const { client, pseudonymKey } = runtime();
  return handleIdentify(request, { client, pseudonymKey });
}

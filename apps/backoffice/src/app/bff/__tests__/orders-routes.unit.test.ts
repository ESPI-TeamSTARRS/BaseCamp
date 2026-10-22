import { beforeEach, describe, expect, it, vi } from 'vitest';

const handleOrders = vi.fn();
const deps = { shop: { id: 'shop' } };

vi.mock('@/lib/handlers/order-handlers', () => ({ handleOrders }));
vi.mock('@/lib/runtime', () => ({ runtime: () => deps }));

const request = (path: string, method = 'GET') =>
  new Request(`http://admin.localhost/bff/orders${path}`, { method });
const context = { params: Promise.resolve({ id: 'cmd-1' }) };

describe('routes des commandes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    handleOrders.mockResolvedValue(new Response(null, { status: 200 }));
  });

  it('GET /bff/orders : liste', async () => {
    const { GET, ...others } = await import('../orders/route');
    const incoming = request('');

    await GET(incoming);

    expect(handleOrders).toHaveBeenCalledWith(incoming, 'list', undefined, deps);
    expect(Object.keys(others).filter((name) => name !== 'dynamic')).toEqual([]);
  });

  it('GET /bff/orders/[id] : détail, et aucune écriture', async () => {
    const { GET, ...others } = await import('../orders/[id]/route');
    const incoming = request('/cmd-1');

    await GET(incoming, context);

    expect(handleOrders).toHaveBeenCalledWith(incoming, 'get', 'cmd-1', deps);
    expect(Object.keys(others).filter((name) => name !== 'dynamic')).toEqual([]);
  });
});

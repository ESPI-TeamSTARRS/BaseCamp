import { beforeEach, describe, expect, it, vi } from 'vitest';

const handleCatalog = vi.fn();
const deps = { shop: { id: 'shop' } };

vi.mock('@/lib/handlers/catalog-handlers', () => ({ handleCatalog }));
vi.mock('@/lib/runtime', () => ({ runtime: () => deps }));

const request = (method: string) => new Request('http://mercure.localhost/bff/products', { method });
const context = { params: Promise.resolve({ id: 'tente-tunnel' }) };

describe('routes du catalogue', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    handleCatalog.mockResolvedValue(new Response(null, { status: 200 }));
  });

  it('GET et POST /bff/products : liste et création', async () => {
    const { GET, POST } = await import('../products/route');
    const list = request('GET');
    const create = request('POST');

    await GET(list);
    await POST(create);

    expect(handleCatalog).toHaveBeenNthCalledWith(1, list, 'list', undefined, deps);
    expect(handleCatalog).toHaveBeenNthCalledWith(2, create, 'create', undefined, deps);
  });

  it('GET et PATCH /bff/products/[id] : lecture et modification', async () => {
    const { GET, PATCH } = await import('../products/[id]/route');
    const read = request('GET');
    const update = request('PATCH');

    await GET(read, context);
    await PATCH(update, context);

    expect(handleCatalog).toHaveBeenNthCalledWith(1, read, 'get', 'tente-tunnel', deps);
    expect(handleCatalog).toHaveBeenNthCalledWith(2, update, 'update', 'tente-tunnel', deps);
  });

  it('POST /bff/products/[id]/archive et /image', async () => {
    const archive = await import('../products/[id]/archive/route');
    const image = await import('../products/[id]/image/route');
    const incoming = request('POST');

    await archive.POST(incoming, context);
    await image.POST(incoming, context);

    expect(handleCatalog).toHaveBeenNthCalledWith(1, incoming, 'archive', 'tente-tunnel', deps);
    expect(handleCatalog).toHaveBeenNthCalledWith(2, incoming, 'image', 'tente-tunnel', deps);
  });
});

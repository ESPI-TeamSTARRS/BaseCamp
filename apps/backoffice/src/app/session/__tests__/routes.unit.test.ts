import { beforeEach, describe, expect, it, vi } from 'vitest';

const handlers = { handleIdentify: vi.fn(), handleFace: vi.fn(), handlePassword: vi.fn() };
const handleLogout = vi.fn();
const deps = { client: { id: 'client' }, pseudonymKey: 'cle' };

vi.mock('@/lib/handlers/login-steps', () => handlers);
vi.mock('@/lib/handlers/logout-handler', () => ({ handleLogout }));
vi.mock('@/lib/runtime', () => ({ runtime: () => ({ ...deps, sessions: {} }) }));

const request = (path: string) => new Request(`http://admin.localhost${path}`, { method: 'POST' });

describe('routes de session', () => {
  beforeEach(() => vi.clearAllMocks());

  it.each([
    ['identify', 'handleIdentify'],
    ['face', 'handleFace'],
    ['password', 'handlePassword'],
  ] as const)(
    'POST /session/%s délègue au gestionnaire avec les dépendances du runtime',
    async (step, name) => {
      handlers[name].mockResolvedValue(new Response(null, { status: 200 }));
      const { POST } = await import(`../${step}/route`);
      const incoming = request(`/session/${step}`);

      const response = await POST(incoming);

      expect(response.status).toBe(200);
      expect(handlers[name]).toHaveBeenCalledWith(incoming, deps);
    }
  );

  it('POST /session/logout délègue au gestionnaire', async () => {
    handleLogout.mockReturnValue(new Response(null, { status: 303 }));
    const { POST } = await import('../logout/route');
    const incoming = request('/session/logout');

    expect(POST(incoming).status).toBe(303);
    expect(handleLogout).toHaveBeenCalledWith(incoming);
  });
});

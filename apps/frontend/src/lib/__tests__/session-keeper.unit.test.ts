import { afterEach, describe, expect, it, vi } from 'vitest';
import { createSessionKeeper, refreshOnce, signOut } from '../session-keeper';
import { clearSession, getAccessToken, setSession } from '../session-store';

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

const ok = (token: string) =>
  jsonResponse({ access_token: token, token_type: 'Bearer', expires_in: 900 }, 200);

class Timers {
  pending: { callback: () => void; delay: number; id: number }[] = [];
  private next = 1;
  set = (callback: () => void, delay: number): unknown => {
    const id = this.next++;
    this.pending.push({ callback, delay, id });
    return id;
  };
  clear = (handle: unknown): void => {
    this.pending = this.pending.filter((timer) => timer.id !== handle);
  };
  async fire(): Promise<void> {
    const timer = this.pending.shift();
    timer?.callback();
    await vi.waitFor(() => undefined);
    await Promise.resolve();
  }
}

afterEach(() => {
  clearSession();
});

describe('refreshOnce', () => {
  it('partage une seule requete entre deux appels simultanes', async () => {
    const fetchImpl = vi.fn().mockImplementation(async () => ok('neuf'));

    const [first, second] = await Promise.all([refreshOnce(fetchImpl), refreshOnce(fetchImpl)]);

    expect([first, second]).toEqual(['refreshed', 'refreshed']);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(getAccessToken()).toBe('neuf');
  });

  it('permet un nouveau rafraichissement une fois le premier termine', async () => {
    const fetchImpl = vi.fn().mockImplementation(async () => ok('neuf'));

    await refreshOnce(fetchImpl);
    await refreshOnce(fetchImpl);

    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it('efface la session sur un 401 mais la garde si le service est indisponible', async () => {
    setSession('ancien', 900);
    expect(await refreshOnce(vi.fn().mockResolvedValue(new Response('', { status: 503 })))).toBe(
      'unavailable'
    );
    expect(getAccessToken()).toBe('ancien');

    expect(await refreshOnce(vi.fn().mockResolvedValue(jsonResponse({}, 401)))).toBe('expired');
    expect(getAccessToken()).toBeNull();
  });
});

describe('signOut', () => {
  it('revoque cote serveur puis efface le jeton en memoire', async () => {
    setSession('jeton', 900);
    const fetchImpl = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));

    await signOut(fetchImpl);

    expect(fetchImpl.mock.calls[0][0]).toBe('/api/auth/logout');
    expect(getAccessToken()).toBeNull();
  });
});

describe('createSessionKeeper', () => {
  it('retrouve la session au chargement grace au cookie', async () => {
    const timers = new Timers();
    const onExpired = vi.fn();
    const keeper = createSessionKeeper({
      fetchImpl: vi.fn().mockImplementation(async () => ok('retrouve')),
      onExpired,
      setTimer: timers.set,
      clearTimer: timers.clear,
    });

    expect(await keeper.start()).toBe('refreshed');

    expect(getAccessToken()).toBe('retrouve');
    expect(onExpired).not.toHaveBeenCalled();
    keeper.stop();
  });

  it('programme le rafraichissement une minute avant l expiration', async () => {
    const timers = new Timers();
    const keeper = createSessionKeeper({
      fetchImpl: vi.fn().mockImplementation(async () => ok('retrouve')),
      onExpired: vi.fn(),
      now: () => Date.now(),
      setTimer: timers.set,
      clearTimer: timers.clear,
    });

    await keeper.start();

    expect(timers.pending).toHaveLength(1);
    expect(timers.pending[0].delay).toBeGreaterThan(830_000);
    expect(timers.pending[0].delay).toBeLessThanOrEqual(840_000);
    keeper.stop();
  });

  it('rafraichit en silence a l echeance puis reprogramme', async () => {
    const timers = new Timers();
    const fetchImpl = vi.fn().mockImplementation(async () => ok('suite'));
    const keeper = createSessionKeeper({
      fetchImpl,
      onExpired: vi.fn(),
      setTimer: timers.set,
      clearTimer: timers.clear,
    });
    await keeper.start();

    await timers.fire();
    await vi.waitFor(() => expect(fetchImpl).toHaveBeenCalledTimes(2));

    await vi.waitFor(() => expect(timers.pending).toHaveLength(1));
    keeper.stop();
  });

  it('programme aussi une session ouverte par la connexion', async () => {
    const timers = new Timers();
    const keeper = createSessionKeeper({
      fetchImpl: vi.fn().mockResolvedValue(jsonResponse({}, 401)),
      onExpired: vi.fn(),
      setTimer: timers.set,
      clearTimer: timers.clear,
    });
    await keeper.start();
    expect(timers.pending).toHaveLength(0);

    setSession('connecte', 900);

    expect(timers.pending).toHaveLength(1);
    keeper.stop();
  });

  it('ne redirige pas un visiteur anonyme dont le chargement n a pas de cookie', async () => {
    const timers = new Timers();
    const onExpired = vi.fn();
    const keeper = createSessionKeeper({
      fetchImpl: vi.fn().mockResolvedValue(jsonResponse({}, 401)),
      onExpired,
      setTimer: timers.set,
      clearTimer: timers.clear,
    });

    expect(await keeper.start()).toBe('expired');

    expect(onExpired).not.toHaveBeenCalled();
    expect(timers.pending).toHaveLength(0);
    keeper.stop();
  });

  it('redirige une fois, sans boucle, quand une session ouverte expire', async () => {
    const timers = new Timers();
    const onExpired = vi.fn();
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({}, 401));
    const keeper = createSessionKeeper({
      fetchImpl,
      onExpired,
      setTimer: timers.set,
      clearTimer: timers.clear,
    });
    await keeper.start();
    setSession('ouverte', 900);

    await timers.fire();
    await vi.waitFor(() => expect(onExpired).toHaveBeenCalledTimes(1));

    expect(timers.pending).toHaveLength(0);
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    keeper.stop();
  });

  it('reessaie un nombre borne de fois quand le service est indisponible', async () => {
    const timers = new Timers();
    const onExpired = vi.fn();
    const fetchImpl = vi.fn().mockResolvedValue(new Response('', { status: 503 }));
    const keeper = createSessionKeeper({
      fetchImpl,
      onExpired,
      setTimer: timers.set,
      clearTimer: timers.clear,
    });

    expect(await keeper.start()).toBe('unavailable');
    for (let i = 0; i < 5; i += 1) {
      await timers.fire();
      await vi.waitFor(() => undefined);
    }

    expect(fetchImpl.mock.calls.length).toBeLessThanOrEqual(4);
    expect(onExpired).not.toHaveBeenCalled();
    expect(timers.pending).toHaveLength(0);
    keeper.stop();
  });

  it('n agit plus une fois arrete', async () => {
    const timers = new Timers();
    const onExpired = vi.fn();
    const keeper = createSessionKeeper({
      fetchImpl: vi.fn().mockResolvedValue(jsonResponse({}, 401)),
      onExpired,
      setTimer: timers.set,
      clearTimer: timers.clear,
    });
    await keeper.start();
    keeper.stop();

    setSession('apres', 900);

    expect(timers.pending).toHaveLength(0);
    expect(onExpired).not.toHaveBeenCalled();
  });
});

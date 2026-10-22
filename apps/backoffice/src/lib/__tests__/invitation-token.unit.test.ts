// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { takeInvitationToken } from '../invitation-token';

const TOKEN = `${'abcdef'.repeat(4)}_-${'0123456789'.repeat(2)}`;

function at(url: string) {
  const location = new URL(url) as unknown as Location;
  const history = { replaceState: vi.fn() } as unknown as History;
  return { location, history };
}

describe('takeInvitationToken', () => {
  it('lit le jeton du fragment et le retire de l’adresse', () => {
    const { location, history } = at(`https://admin.example.test/invitation#token=${TOKEN}`);

    expect(takeInvitationToken(location, history)).toBe(TOKEN);
    expect(history.replaceState).toHaveBeenCalledWith(null, '', '/invitation');
  });

  it('accepte aussi le paramètre ?token= et le retire', () => {
    const { location, history } = at(`https://admin.example.test/invitation?token=${TOKEN}&x=1`);

    expect(takeInvitationToken(location, history)).toBe(TOKEN);
    expect(history.replaceState).toHaveBeenCalledWith(null, '', '/invitation?x=1');
  });

  it.each([
    ['sans jeton', 'https://admin.example.test/invitation'],
    ['jeton trop court', 'https://admin.example.test/invitation#token=abc'],
    ['caractères interdits', 'https://admin.example.test/invitation#token=' + 'a'.repeat(20) + '<script>'],
    ['jeton vide', 'https://admin.example.test/invitation#token='],
  ])('refuse : %s', (_name, url) => {
    const { location, history } = at(url);

    expect(takeInvitationToken(location, history)).toBeNull();
    expect(history.replaceState).toHaveBeenCalled();
  });
});

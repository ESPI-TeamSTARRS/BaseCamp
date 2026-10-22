import { describe, expect, it } from 'vitest';
import { metadata } from '../layout';
import { LoginForm } from '../login/login-form';
import LoginPage from '../login/page';
import robots from '../robots';

describe('pages du back-office', () => {
  it('robots.txt interdit tout', () => {
    expect(robots()).toEqual({ rules: { userAgent: '*', disallow: '/' } });
  });

  it('les métadonnées portent noindex', () => {
    expect(metadata.robots).toMatchObject({ index: false, follow: false });
  });

  it('la page de connexion rend l’écran à trois temps', () => {
    const element = LoginPage() as { type: unknown };
    expect(element.type).toBe(LoginForm);
  });
});

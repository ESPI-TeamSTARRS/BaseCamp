import { describe, expect, it } from 'vitest';
import { metadata } from '../layout';
import LoginPage from '../login/page';
import HomePage from '../page';
import robots from '../robots';

describe('pages du back-office', () => {
  it('robots.txt interdit tout', () => {
    expect(robots()).toEqual({ rules: { userAgent: '*', disallow: '/' } });
  });

  it('les métadonnées portent noindex', () => {
    expect(metadata.robots).toMatchObject({ index: false, follow: false });
  });

  it('la page d’accueil se rend', () => {
    expect(HomePage()).toBeTruthy();
  });

  it('la page de connexion annonce les trois temps et n’affiche une alerte que pour une erreur connue', async () => {
    const render = async (erreur?: string) =>
      JSON.stringify(await LoginPage({ searchParams: Promise.resolve({ erreur }) }));

    expect(await render()).toContain('trois temps');
    expect(await render()).not.toContain('alert');
    expect(await render('2')).toContain('momentanément indisponible');
    expect(await render('999')).not.toContain('alert');
  });
});

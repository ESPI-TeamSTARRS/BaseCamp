import { describe, expect, it } from 'vitest';
import { metadata } from '../layout';
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
});

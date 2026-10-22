import { describe, expect, it } from 'vitest';
import { categorySlugs } from '../categories';
import { footerSections, indexablePages } from '../footer-links';

describe('liens du pied de page', () => {
  it('présente les catégories, le service client et le légal, dans cet ordre', () => {
    expect(footerSections.map((section) => section.title)).toEqual(['Catégories', 'Service client', 'Légal']);
  });

  it('une entrée par catégorie du catalogue, vers sa page', () => {
    const [categories] = footerSections;

    expect(categories.links.map((link) => link.href)).toEqual(
      categorySlugs.map((slug) => `/categories/${slug}`)
    );
    expect(categories.links.map((link) => link.label)).toContain('Tentes & Abris');
  });

  it('expose les pages de service et les pages légales attendues', () => {
    const links = Object.fromEntries(
      footerSections.slice(1).flatMap((section) => section.links.map((l) => [l.label, l.href]))
    );

    expect(links).toEqual({
      'Suivre ma commande': '/suivi',
      Contact: '/contact',
      CGV: '/cgv',
      Confidentialité: '/confidentialite',
      'Mentions légales': '/mentions-legales',
    });
  });

  it('chaque lien est un chemin interne sans doublon', () => {
    const hrefs = footerSections.flatMap((section) => section.links.map((link) => link.href));

    expect(new Set(hrefs).size).toBe(hrefs.length);
    for (const href of hrefs) expect(href).toMatch(/^\/[a-z0-9\-/]+$/);
  });

  it('les pages de contenu sont indexables dans le plan du site', () => {
    expect(indexablePages).toEqual(['/suivi', '/contact', '/cgv', '/confidentialite', '/mentions-legales']);
  });
});

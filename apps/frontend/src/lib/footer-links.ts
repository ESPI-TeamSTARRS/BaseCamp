import { categoryLabels, categorySlugs } from './categories';

// Liens du pied de page : une seule source pour l'affichage et pour le plan du site.

export interface FooterLink {
  label: string;
  href: string;
}

export interface FooterSection {
  title: string;
  links: FooterLink[];
}

export const footerSections: FooterSection[] = [
  {
    title: 'Catégories',
    links: categorySlugs.map((slug) => ({ label: categoryLabels[slug], href: `/categories/${slug}` })),
  },
  {
    title: 'Service client',
    links: [
      { label: 'Suivre ma commande', href: '/suivi' },
      { label: 'Contact', href: '/contact' },
      { label: 'CGV', href: '/cgv' },
    ],
  },
  {
    title: 'Légal',
    links: [
      { label: 'Confidentialité', href: '/confidentialite' },
      { label: 'Mentions légales', href: '/mentions-legales' },
    ],
  },
];

/** Pages de contenu (hors catégories) à publier dans le plan du site. */
export const indexablePages: string[] = footerSections
  .slice(1)
  .flatMap((section) => section.links.map((link) => link.href));

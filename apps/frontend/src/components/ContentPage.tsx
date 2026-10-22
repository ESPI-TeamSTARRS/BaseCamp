import type { ReactNode } from 'react';

interface ContentPageProps {
  title: string;
  updatedAt?: string;
  narrow?: boolean;
  children: ReactNode;
}

/** Mise en page commune des pages de contenu : un seul h1, bandeau pédagogique, date de mise à jour. */
export function ContentPage({ title, updatedAt, narrow = false, children }: ContentPageProps) {
  return (
    <section className={`mx-auto px-4 py-16 ${narrow ? 'max-w-xl' : 'max-w-2xl'}`}>
      <p
        role="note"
        className="mb-6 rounded-lg border border-bivouac/30 bg-sand-dark px-4 py-3 text-sm text-granite"
      >
        Projet pédagogique : les informations de cette page sont fictives.
      </p>
      <h1 className="mb-2 text-3xl font-bold text-granite">{title}</h1>
      {updatedAt && <p className="mb-8 text-sm text-granite/60">Dernière mise à jour : {updatedAt}</p>}
      <div className="space-y-8 text-granite/80">{children}</div>
    </section>
  );
}

/** Rubrique d'une page de contenu : titre de niveau 2 et paragraphes. */
export function ContentSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="mb-3 text-xl font-semibold text-granite">{title}</h2>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

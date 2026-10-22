import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { LoginForm } from '../LoginForm';

describe('LoginForm : liens', () => {
  const html = renderToStaticMarkup(<LoginForm />);

  it('propose « Mot de passe oublié ? » vers la page de demande de lien', () => {
    expect(html).toMatch(/<a [^>]*href="\/compte\/mot-de-passe-oublie"[^>]*>Mot de passe oublié \?<\/a>/);
  });

  it('place ce lien avant le bouton de connexion, près du champ du mot de passe', () => {
    expect(html.indexOf('Mot de passe oublié ?')).toBeGreaterThan(html.indexOf('id="password"'));
    expect(html.indexOf('Mot de passe oublié ?')).toBeLessThan(html.indexOf('Me connecter</button>'));
  });

  it('garde le lien « Créer mon compte »', () => {
    expect(html).toMatch(/href="\/compte\/inscription"[^>]*>Créer mon compte</);
  });
});

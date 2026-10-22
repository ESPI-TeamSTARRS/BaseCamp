// Jeton du lien d'invitation : lu une seule fois puis retire de l'adresse affichee.
// Le lien genere par l'administrateur le porte dans le fragment (`#token=...`), que le navigateur
// n'envoie jamais au serveur; la forme `?token=...` est aussi acceptee.

const TOKEN_PATTERN = /^[A-Za-z0-9_-]{16,256}$/;

function valid(candidate: string | null): string | null {
  return candidate !== null && TOKEN_PATTERN.test(candidate) ? candidate : null;
}

/** Lit le jeton, puis efface fragment et parametre de l'adresse (historique compris). */
export function takeInvitationToken(location: Location, history: History): string | null {
  const fromHash = valid(new URLSearchParams(location.hash.replace(/^#/, '')).get('token'));
  const fromQuery = valid(new URLSearchParams(location.search).get('token'));
  const clean = new URL(location.href);
  clean.hash = '';
  clean.searchParams.delete('token');
  history.replaceState(null, '', `${clean.pathname}${clean.search}`);
  return fromHash ?? fromQuery;
}

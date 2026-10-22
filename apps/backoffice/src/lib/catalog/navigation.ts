// Retour a la connexion quand la session a expire pendant un appel (isole pour etre remplace en test).
export function redirectToLogin(): void {
  // Navigation complete voulue : elle repart d'une page neuve, sans etat de l'ecran precedent.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  window.location.href = '/login';
}

// Libelles et dates des commandes : les statuts sont pilotes par le paiement, jamais modifies ici.

export const STATUS_LABELS: Record<string, string> = {
  pending_payment: 'En attente de paiement',
  paid: 'Payée',
  expired: 'Expirée',
  refunded: 'Remboursée',
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

const DATE_TIME = new Intl.DateTimeFormat('fr-FR', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  timeZone: 'Europe/Paris',
});

/** Date de commande en heure de Paris ; un horodatage sans fuseau est lu comme UTC (c'est ce que stocke shop). */
export function formatDateTime(value: string): string {
  const zoned = /(Z|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`;
  const date = new Date(zoned);
  if (Number.isNaN(date.getTime())) return value;
  return DATE_TIME.format(date).replace(' à ', ', ').replace(/ /g, ' ');
}

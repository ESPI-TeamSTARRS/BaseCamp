export function CatalogUnavailable() {
  return (
    <div
      role="alert"
      className="rounded-card border border-bivouac/30 bg-bivouac/10 p-6 text-granite"
      data-testid="catalog-unavailable"
    >
      <p className="font-semibold">Le catalogue est momentanément indisponible.</p>
      <p className="mt-1 text-sm text-granite/70">
        Nous n&apos;arrivons pas à charger les produits pour le moment. Merci de réessayer dans quelques
        instants.
      </p>
    </div>
  );
}

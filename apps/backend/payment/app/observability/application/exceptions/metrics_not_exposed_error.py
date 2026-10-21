class MetricsNotExposedError(Exception):
    """Les metriques ne sont servies qu'en direct sur le reseau interne, jamais via un proxy."""

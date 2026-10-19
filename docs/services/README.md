# Services

Un document par service, avec la même trame : rôle, responsabilités, API, configuration, invariants.

- [shop](shop.md)
- [auth](auth.md)
- [payment](payment.md)
- [frontend](frontend.md)

Tous les services backend exposent `GET /health` (liveness) et se configurent par variables d'environnement préfixées `APP_` (`APP_SERVICE_NAME`, `APP_ENVIRONMENT`).

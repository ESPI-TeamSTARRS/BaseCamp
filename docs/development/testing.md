# TDD et tests

## Cycle Red, Green, Blue

Aucun code d'implémentation sans test en échec au préalable, une règle métier à la fois.

1. **Red** : écrire le test (Étant donné / Quand / Alors), vérifier qu'il échoue. Commit `test(<scope>): red — <règle>`.
2. **Green** : l'implémentation la plus simple qui passe. Commit `feat(<scope>): green — <règle>` (`fix` pour un bug).
3. **Blue** : refactorer en relançant les tests à chaque changement; un test qui échoue impose d'annuler le dernier changement. Commit `refactor(<scope>): blue — <changement>`.

## Niveaux et nommage

Les tests unitaires et d'intégration sont colocalisés avec le code, dans des dossiers `__tests__/`.

| Niveau | Contenu | Back | Front |
|---|---|---|---|
| unit | entités, value objects, cas d'usage avec dépôts simulés, mappers | `test_<règle>.unit.py` | `<nom>.unit.test.ts(x)` |
| integ | routeur HTTP en mémoire, dépôt avec vraie base, composant avec API simulée | `test_<règle>.integ.py` | `<nom>.integ.test.ts(x)` |
| e2e | parcours complet sur la stack lancée | `tests/e2e/scenarios/test_<parcours>.e2e.py` | `tests/e2e/` |

Côté back, `conftest.py` pose automatiquement le marker pytest (`unit`, `integ`, `e2e`) d'après le suffixe, ce qui permet `pytest -m unit`.

## Couverture

Seuil bloquant de 80 % (back : `--cov-fail-under=80` avec branches; front : `thresholds` de `vitest.config.ts`), 90 % visé sur la logique métier. Le périmètre de couverture du front (`coverage.include`) s'étend avec chaque fonctionnalité; on n'exclut jamais de code pour faire monter le chiffre.

## Commandes

```bash
# back, dans apps/backend/<service>
uv run poe test:unit    # boucle TDD rapide
uv run poe test         # tout, avec couverture
uv run poe check        # lint + format + types + sécurité + tests

# front, dans apps/frontend
npm run test:unit
npm run test:coverage
```

## À tester en priorité (paiement)

Idempotence, montant et devise valides, remboursement inférieur ou égal au montant capturé restant, signature de webhook invalide rejetée, rejeu d'événement ignoré, cohérence commande payée et transaction.

## Concurrence sur Postgres

Le test de concurrence des commandes (`test_order_concurrency.integ.py`) a besoin d'un vrai Postgres (SQLite ne verrouille pas les lignes). Il est ignoré sans la variable `APP_TEST_POSTGRES_URL` (fournie par le service Postgres du job `backend` en CI). En local : lancer un Postgres jetable de son choix et exporter l'URL `postgresql+psycopg://…` avant `uv run poe test`.

## Scénarios e2e de la pile

Un scénario e2e vit dans `apps/backend/shop/tests/e2e/scenarios/test_<parcours>.e2e.py` et parle à la pile Docker Compose réelle **par la passerelle Traefik**, avec `httpx` (jamais directement aux services). Il lit l'URL de la passerelle dans `E2E_BASE_URL`; sans cette variable, les scénarios sont ignorés, donc `poe test` ne dépend pas de la pile.

```bash
cp .env.example .env
docker compose up -d --wait traefik          # pile minimale
cd apps/backend/shop
E2E_BASE_URL=http://127.0.0.1:8080 uv run poe test:e2e
```

Écrire d'abord le scénario (Red) avant d'ajouter la route ou le service qu'il exerce. Chaque scénario nettoie ses données et ne suppose pas d'ordre d'exécution. Les parcours navigateur (Playwright) sont hors de ce périmètre. En CI, voir le job `stack-e2e` dans [ci.md](ci.md).

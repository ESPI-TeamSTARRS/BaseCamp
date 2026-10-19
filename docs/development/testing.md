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

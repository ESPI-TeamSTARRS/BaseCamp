---
name: tdd-couverture
description: TDD strict (Red, Green, Blue) avec tests colocalises unit/integ/e2e et couverture superieure a 80 % pour le back (pytest) et le front (vitest) de Basecamp. A utiliser AVANT d'ecrire du code d'implementation, pour toute fonctionnalite, correction ou refactoring.
---

# TDD strict + tests colocalises + couverture > 80 %

Aucun code d'implementation sans test rouge d'abord. Un commit par phase.

## Cycle (une regle metier a la fois)

1. **RED** : ecrire un test qui exprime la regle (Etant donne / Quand / Alors). Le lancer : il doit echouer pour la bonne raison. Commit `test(<scope>): red — <regle>`.
2. **GREEN** : l'implementation la plus simple qui passe. Pas d'optimisation. Commit `feat(<scope>): green — <regle>` (`fix(...)` pour un bug).
3. **BLUE** : refactorer en relancant les tests apres chaque changement. Si un test passe au rouge, annuler le dernier changement. Commit `refactor(<scope>): blue — <changement>`.

Criteres de sortie du BLUE : noms explicites, fonctions <= 20 lignes, retours anticipes, pas de valeur magique (enums), types explicites, exceptions de domaine typees, 1 fichier = 1 classe, lint et types a 0 erreur.

## Niveaux de test et nommage

| Niveau | Quoi | Back (`apps/backend/<service>`) | Front (`apps/frontend`) |
|---|---|---|---|
| unit | entites, value objects, cas d'usage (depots simules), mappers | `app/<tranche>/__tests__/unit/test_<regle>.unit.py` | `src/**/__tests__/<nom>.unit.test.ts(x)` |
| integ | routeur HTTP in-process (httpx ASGI), depot + vraie BDD, composant + API simulee | `.../__tests__/integration/test_<regle>.integ.py` | `src/**/__tests__/<nom>.integ.test.ts(x)` |
| e2e | parcours complet sur la stack lancee | `tests/e2e/scenarios/test_<parcours>.e2e.py` | `tests/e2e/` (Playwright) |

Les tests unit/integ sont **colocalises** avec le code. Le suffixe est la source de verite du niveau : `conftest.py` pose automatiquement le marker pytest (`unit`, `integ`, `e2e`).

## Commandes

```bash
# Back, dans apps/backend/<service> (ou via la racine : uv run poe test)
uv run poe test:unit     # boucle TDD rapide, sans couverture
uv run poe test          # tout + couverture, echoue sous 80 %
uv run poe check         # lint + format + types + securite + tests

# Front, dans apps/frontend
npm run test:unit        # boucle rapide
npm run test:coverage    # echoue sous 80 %

# Tout le monorepo, depuis la racine
uv run poe ci
```

## Couverture

- **Seuil bloquant : 80 % global** (back : `--cov-fail-under=80` avec branches; front : `thresholds` dans `vitest.config.ts`).
- Viser **90 %** sur la logique metier (domaine + cas d'usage).
- Le perimetre front (`coverage.include` dans `vitest.config.ts`) s'elargit a chaque fonctionnalite livree : ajouter les nouveaux fichiers metier, ne jamais exclure du code pour faire monter le chiffre.
- Un test de non-regression accompagne chaque bug corrige.

## Quoi tester en priorite (paiement)

Idempotence (meme cle = meme resultat, pas de doublon), montant et devise valides, remboursement <= montant capture restant, signature de webhook invalide rejetee, rejeu d'evenement ignore, coherence commande payee = transaction.

## Rappels

- Une regle a la fois : pas 5 tests puis 5 implementations.
- Ne jamais modifier un test pour le faire passer; corriger l'implementation.
- Les tests d'architecture (`test_architecture.unit.py`) font partie de la suite : ils doivent rester verts.
- Hooks Git : `pre-commit` (secrets, lint, format), `pre-push` (types + tests unitaires), `commit-msg` (Conventional Commit). CI : `.github/workflows/ci.yml`.

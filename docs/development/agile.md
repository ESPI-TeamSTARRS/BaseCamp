# Gestion de projet agile

Cadre léger pour une petite équipe qui livre en itérations très courtes (quelques jours). Il applique les valeurs et principes du [manifeste agile](https://agilemanifesto.org/iso/fr/manifesto.html) sans cérémonie superflue.

## Valeurs, appliquées ici

| Valeur du manifeste | Ce que ça change concrètement |
|---|---|
| Individus et interactions plutôt que processus et outils | Un point quotidien court, des décisions prises à voix haute; l'outil (Linear) sert l'équipe, pas l'inverse |
| Logiciel opérationnel plutôt que documentation exhaustive | Chaque ticket fini est du code déployable sur `main`; la documentation reste celle de l'application (`docs/`) |
| Collaboration avec le client plutôt que négociation contractuelle | Les critères d'acceptation se discutent et se vérifient ensemble avant de coder |
| Réagir au changement plutôt que suivre un plan | Le périmètre se réajuste chaque jour; on retire ou on ajoute des tickets sans renégocier tout le plan |

## Principes retenus

1. **Livrer tôt et souvent** : petites PR, `main` toujours déployable ([git-and-hooks.md](git-and-hooks.md)).
2. **Accueillir le changement**, même tardif, en réordonnant le backlog plutôt qu'en défendant le plan.
3. **Le logiciel qui fonctionne est la mesure d'avancement** : un ticket est terminé quand il est en `main`, testé, pas quand le code est écrit.
4. **Rythme soutenable** et **simplicité** : ne pas faire ce qui n'est pas nécessaire (art de maximiser le travail non fait).
5. **Excellence technique continue** : TDD, Clean Architecture, qualité automatisée ([rules.md](rules.md)).
6. **Équipe auto-organisée** : chacun prend le ticket prêt de plus haute priorité dans son domaine; les arbitrages se font en équipe.
7. **Rétrospective régulière** : on ajuste la façon de travailler.

## Outil et identifiants

Les tickets vivent dans Linear, équipe **WORK** (`WORK-<n>`). L'identifiant figure dans la branche (`feat/WORK-<n>-<slug>`), les commits et le titre de PR. L'état d'un ticket (À faire, En cours, En revue, Terminé) se tient dans Linear, jamais dans le dépôt. Rédaction des tickets : [tickets.md](tickets.md).

## Rituels légers

| Rituel | Quand | Durée | Contenu |
|---|---|---|---|
| Cadrage de l'itération | Début | 30 à 45 min | Objectif de l'itération, tickets prioritaires, découpage, risques |
| Point quotidien | Chaque jour | 10 min | Fait, prévu, blocages. Aucun détail technique long |
| Affinage | À la volée | 10 à 15 min | Découper les tickets trop gros, vérifier la définition de prêt |
| Revue de fin de journée ou d'itération | Fin | 15 min | Démonstration de ce qui tourne sur `main` |
| Rétrospective | Fin d'itération | 15 min | Ce qui a marché, ce qui frotte, une action concrète |

## Priorisation

Ordre de décision, du plus fort au plus faible :

1. Ce qui bloque les autres ou la livraison (dépendances, CI rouge, incident).
2. Ce qui apporte la plus grande valeur utilisateur par unité d'effort.
3. Ce qui réduit un risque de sécurité ou d'intégrité (paiement, authentification).
4. Le reste, par ordre d'effort croissant.

Priorités Linear : Urgente (bloquant), Haute (cœur de l'objectif), Moyenne, Basse. Un seul ticket en cours par personne; on termine avant de commencer.

## Définition de prêt

Un ticket peut être pris quand :

- l'objectif et la valeur sont clairs (user story ou objectif technique);
- les critères d'acceptation sont vérifiables (Étant donné / Quand / Alors);
- le périmètre et le hors-périmètre sont écrits;
- il tient en une à deux journées, sinon il est découpé;
- ses dépendances sont identifiées et levées ou planifiées;
- les services concernés sont nommés.

## Définition de terminé

Un ticket est terminé quand :

- tous les critères d'acceptation sont satisfaits et couverts par des tests écrits d'abord (TDD);
- la couverture reste ≥ 80 %, lint, types, sécurité et scan de secrets sont verts;
- la PR est relue et fusionnée en squash sur `main`, CI verte;
- le service démarre et répond sur `/health`;
- la documentation de [services/](../services/README.md) est à jour si une API ou un invariant change;
- le ticket est passé à Terminé dans Linear.

## Gestion du changement

- Un nouveau besoin entre dans le backlog sous forme de ticket, évalué par la priorisation ci-dessus.
- Si le besoin dépasse la capacité, on décide ce qui sort : on ne rallonge pas la journée.
- Un changement qui touche l'architecture suit [architecture/services-and-gateway.md](../architecture/services-and-gateway.md); si une règle doit évoluer, on modifie d'abord le document concerné dans la même PR.
- Un ticket qui grossit en cours de route est arrêté, découpé, et la partie non livrée devient un nouveau ticket.

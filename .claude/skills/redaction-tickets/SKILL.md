---
name: redaction-tickets
description: Redige un ticket Linear (equipe WORK) a partir d'un besoin precis, comme une equipe agile en entreprise, avec double vision metier et technique (valeur utilisateur, user story, criteres d'acceptation Given/When/Then, perimetre, decoupage par service, exigences de qualite, taches techniques, risques, estimation). A utiliser avant de creer ou de decouper tout ticket. Ne cree jamais un ticket dans Linear sans avoir montre le texte a Sam.
---

# Rédaction de tickets — équipe WORK

Cadre : [docs/development/agile.md](../../../docs/development/agile.md) (valeurs, prêt/terminé, priorisation) et [docs/development/tickets.md](../../../docs/development/tickets.md) (anatomie d'un ticket). En cas de divergence, les docs font foi. Le lien avec Git est dans le skill `git-trunk-based`.

## Règle absolue

**Montrer le texte du ticket à Sam et attendre son accord avant toute création ou modification dans Linear.** Rédiger dans la conversation d'abord. Après accord seulement : créer via le connecteur Linear (équipe `WORK`), en créant le parent avant ses sous-tickets.

## Démarche

1. **Comprendre le besoin** : qui en a besoin, quel problème, comment on saura que c'est réussi. Si une réponse manque et change le ticket, poser une question courte; sinon choisir un défaut raisonnable et le dire.
2. **Choisir le type** (convention Sam) :
   - **Story** : apporte de la valeur visible à un utilisateur (page, composant, endpoint consommé par le front, parcours métier).
   - **Tâche** : travail technique sans valeur utilisateur directe (scaffolding, migration, CI, infrastructure, documentation interne, outillage).
   - Ticket mixte non découpé : Story par défaut, mais préférer le découper.
3. **Découper** : un ticket = une intention livrable en une à deux journées, avec une PR petite. Une Story qui touche plusieurs services se découpe en sous-tickets par service (`shop`, `auth`, `payment`, `frontend`), le parent portant la valeur et les critères métier. Appliquer la règle fonctionnalité ou service de `docs/architecture/services-and-gateway.md`; en cas de doute d'architecture, utiliser le skill `architecte`.
4. **Rédiger** avec le gabarit ci-dessous, en français, sans jargon inutile.
5. **Vérifier la définition de prêt** (voir `agile.md`) et le dire.
6. **Présenter à Sam**, avec le plan de découpage et les titres, puis attendre son accord.

## Titre

`WORK-<n> <verbe à l'infinitif ou groupe nominal court>`, par exemple `WORK-12 Rembourser partiellement une commande`. Le numéro est attribué par Linear à la création : dans le brouillon, écrire `WORK-xxx`. Le titre décrit le résultat, pas la technique.

## Gabarit

```markdown
**Type** : Story | Tâche · **Services** : shop, payment · **Priorité** : Urgente | Haute | Moyenne | Basse · **Estimation** : 1 | 2 | 3 | 5

## Contexte et valeur
Pourquoi ce ticket existe, quel problème il résout, pour qui, quel bénéfice mesurable.

## User story
En tant que <rôle>, je veux <action> afin de <bénéfice>.
(Tâche : une phrase décrivant l'objectif technique et ce qu'il débloque.)

## Critères d'acceptation
- [ ] Étant donné <contexte>, quand <action>, alors <résultat vérifiable>.
- [ ] Cas limite ou d'erreur : étant donné …, quand …, alors …
- [ ] ...

## Périmètre
Inclus : …
Hors périmètre : … (ce qui est volontairement exclu, ou renvoyé à un autre ticket)

## Découpage par service
- `shop` : …
- `payment` : …
- `frontend` : …

## Exigences de qualité
- TDD strict (Red, Green, Blue), tests colocalisés unit et integ; e2e si un parcours complet change.
- Couverture ≥ 80 % maintenue (90 % visé sur le domaine et les cas d'usage).
- Test d'architecture et règles de dépendance respectés; aucune dépendance entre services.
- Entrées validées, aucun secret, erreurs assainies.
- Documentation `docs/services/<service>.md` mise à jour si une API ou un invariant change.

## Tâches techniques
- [ ] Écrire les tests (Red) pour …
- [ ] Implémenter … (tranche `<fonctionnalité>` du service `<service>`)
- [ ] Brancher / exposer …
- [ ] Mettre à jour la documentation

## Risques et dépendances
- Dépend de : WORK-xx. Bloque : WORK-yy.
- Risque : … → parade : …

## Définition de terminé
Voir `docs/development/agile.md`. Spécifique à ce ticket : …
```

## Bonnes pratiques

- Critères d'acceptation **vérifiables** : chacun se transforme en test. Pas de « fonctionne bien » ni « rapide ».
- Inclure au moins un cas d'erreur ou limite par ticket métier (par exemple remboursement supérieur au montant restant, clé d'idempotence rejouée).
- Pour le paiement, relire les invariants de `docs/services/payment.md`.
- Estimation en points (1, 2, 3, 5); au-dessus de 5, découper. La taille cible tient en une à deux journées.
- Pas de suivi d'avancement écrit dans le dépôt : l'état d'un ticket vit dans Linear.
- Branche et commit reprennent l'identifiant : `feat/WORK-<n>-<slug>` et `feat(<scope>): … (WORK-<n>)`.

## Création dans Linear (après accord de Sam)

1. Vérifier que le connecteur Linear est actif; sinon le dire à Sam et s'arrêter.
2. Créer le parent, noter son identifiant, puis les sous-tickets liés au parent.
3. Étiquettes : une par service concerné (`shop`, `auth`, `payment`, `frontend`) et le type (`story` ou `tâche`).
4. Rapporter à Sam la liste des tickets créés avec leurs liens.

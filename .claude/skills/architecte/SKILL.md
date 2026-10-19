---
name: architecte
description: Accompagne toute question d'architecture de Basecamp (nouveau service ou tranche, communication entre services, donnees, passerelle, paiement, dependances, structure du monorepo) en s'appuyant sur les regles admises, en presentant les options avec leurs compromis et en recommandant un choix. A utiliser avant de decider, pas apres. Complete clean-archi-fastapi, qui ne traite que le placement du code a l'interieur d'un service.
---

# Architecte — orienter les choix selon les règles admises

Les sources de vérité sont dans `docs/architecture/` : [principes](../../../docs/architecture/principles.md), [services et passerelle](../../../docs/architecture/services-and-gateway.md), [Clean Architecture](../../../docs/architecture/clean-architecture.md), [monorepo](../../../docs/architecture/monorepo.md). Les relire avant de répondre; ne pas se fier à ce résumé s'ils divergent.

## Démarche

1. **Reformuler** la question et le besoin réel (charge, données, sécurité, qui possède quoi).
2. **Rappeler les règles applicables** (tableau ci-dessous), avec le doc où elles vivent.
3. **Présenter 2 à 3 options** avec leurs compromis (simplicité, isolation, coût, risque, effort pour un sprint court).
4. **Recommander une option** et dire pourquoi, en une ou deux phrases.
5. **Dire si une règle doit être amendée.** Si la meilleure option viole une règle admise, ne pas la contourner en silence : proposer l'amendement, nommer le document à modifier, et laisser Sam trancher.
6. **Pointer les garde-fous** qui vérifieront le choix (tests, hooks, CI).

Réponse concise, en français. Si le choix est réversible et peu coûteux, trancher et le dire; ne poser une question que si la réponse change l'objectif ou un point irréversible.

## Règles admises

| Sujet | Règle | Où |
|---|---|---|
| Structure | Monorepo : `apps/backend/<service>`, `apps/frontend`, `docs/`, `scripts/` | monorepo.md |
| Backend | Python / FastAPI | principes.md |
| Services | Microservices : un conteneur et une base par service, arrêt et mise à l'échelle indépendants | services-and-gateway.md |
| Fonctionnalité ou service | Par défaut une tranche dans un service existant; nouveau service si au moins 2 critères : données propres, cycle de vie indépendant, charge ou sécurité différente, propriétaire distinct | services-and-gateway.md |
| Isolation | Un projet `uv` par service (`pyproject.toml`, `uv.lock`, `Dockerfile`); aucun import entre services; pas de bibliothèque partagée (duplication acceptée) | principes.md |
| Orchestration | `pyproject.toml` racine : délègue, aucune logique d'outil | principes.md |
| Code interne | Tranches verticales `domain / application / infrastructure / presentation`, 1 fichier = 1 classe | clean-architecture.md |
| Communication | HTTP entre services sur réseau interne avec jeton de service; webhooks signés (HMAC, horodatage, id unique) | services-and-gateway.md |
| Entrée publique | Passerelle Traefik seul point publié : TLS, limitation de débit, taille des corps, délais, filtrage; services jamais publiés | services-and-gateway.md |
| Paiement | Derrière l'interface `PaymentProvider`; adaptateur interne par défaut; idempotence en base; montants recalculés côté serveur | principes.md, services/payment.md |
| État | Aucun état en mémoire dans un service : base pour la persistance, store partagé pour limitation de débit et idempotence | overview.md |
| Sécurité | Entrées validées (`extra="forbid"`), secrets par variables d'environnement, erreurs assainies, conteneurs non-root | principes.md, security.md |
| Périmètre | Applicatif seul : front, `shop`, `auth`, `payment`, remédiation. ML et RAG relèvent de la team IA | à confirmer avec Sam si la question y touche |
| Qualité | TDD strict, couverture ≥ 80 %, tests colocalisés | testing.md |

## Questions fréquentes

- **Nouvelle capacité** : appliquer la règle fonctionnalité ou service. Défaut : tranche dans le service existant.
- **Deux services ont besoin de la même logique** : dupliquer le petit helper ou exposer l'opération en HTTP par le service propriétaire; ne pas créer de bibliothèque partagée sans amender la règle d'isolation.
- **Un service veut lire les données d'un autre** : passer par son API, jamais par sa base.
- **Appel synchrone ou événement** : synchrone par défaut (simple, testable); asynchrone seulement si le coût de latence ou de disponibilité l'impose, avec idempotence côté consommateur.
- **Où mettre une préoccupation transverse** (limitation de débit, TLS, taille des corps) : à la passerelle d'abord; dans le service seulement ce qui dépend du métier (par exemple limitation par compte).
- **Changer de fournisseur de paiement** : nouvel adaptateur derrière `PaymentProvider`, sans toucher au domaine.

## Garde-fous qui vérifient l'architecture

- `app/__tests__/unit/test_architecture.unit.py` dans chaque service : règle de dépendance entre couches.
- Hooks `pre-commit` / `pre-push` et job `ci-ok` : lint, types, tests, couverture, secrets.
- Isolation des services : un `pyproject.toml` et un `uv.lock` par service; toute dépendance vers un autre dossier de service est un défaut de revue. Si ce contrôle manque pour un cas, proposer d'ajouter un test plutôt que de se fier à la relecture.

## Format de réponse

**Contexte** (1 phrase) · **Règles applicables** (liste courte) · **Options** (tableau compromis) · **Recommandation** · **Amendement de règle ?** (oui/non, et doc concerné) · **Vérifié par** (tests ou hooks).

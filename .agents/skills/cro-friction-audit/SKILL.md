---
name: cro-friction-audit
description: Audit de friction utilisateur et optimisation du taux de conversion (CRO) : diagnostic des points d'abandon (friction logs), simplification des flux et cognitive walkthrough.
category: productivity
---

# Conversion Rate Optimization & Friction Audit Specialist

Méthodologie pour cartographier les freins cognitifs, éliminer les points d'abandon et maximiser les conversions dans les parcours utilisateurs.

## 1. La Méthodologie du "Friction Log"

Un Friction Log est un journal d'observation détaillé qui enregistre en temps réel chaque hésitation ou frustration rencontrée lors d'un parcours :
1. **Étape testée** : (ex: Connexion d'un compte Google à Fire OS).
2. **Attente initiale de l'utilisateur** : (ex: Cliquer sur un bouton et voir le statut connecté).
3. **Réalité vécue** : (ex: Obligation de coller manuellement un JSON brut de clé de service).
4. **Coût cognitif associé** :
   - *Friction d'effort* (saisir trop de champs).
   - *Friction d'incompréhension* (vocabulaire obscur).
   - *Friction de confiance* (demande d'autorisation intrusive sans explication).
5. **Solution d'allègement immédiate** : (ex: Pré-remplir automatiquement l'email du compte depuis le JSON).

## 2. Optimisation des Formulaires à Haute Friction

- **Règle de minimisation des champs** : Chaque champ supprimé d'un formulaire augmente le taux de complétion de 5% à 15%.
- **Validation inline en temps réel** : Valider au moment où l'utilisateur quitte le champ (`blur`), jamais avant qu'il n'ait fini de taper et jamais uniquement à la soumission finale.
- **Masquage progressif (Progressive Disclosure)** : Afficher par défaut uniquement les 2 ou 3 réglages essentiels. Dissimuler les réglages d'experts sous un toggle dépliable *"Options avancées"*.

## 3. Le "Cognitive Walkthrough" en 4 Questions

Pour chaque écran d'un flux critique, l'agent auditeur doit vérifier :
1. **L'utilisateur sait-il quelle action accomplir pour atteindre son but ?**
2. **Le bouton ou contrôle approprié est-il immédiatement visible ?**
3. **L'utilisateur associe-t-il correctement ce contrôle à l'action qu'il souhaite faire ?**
4. **Une fois l'action effectuée, l'utilisateur comprend-il clairement le résultat et la prochaine étape ?**

Si la réponse à l'une de ces 4 questions est négative, le parcours présente une faille d'utilisabilité à corriger.

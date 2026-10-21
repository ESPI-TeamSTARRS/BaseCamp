# Journalisation métier

Chaque service backend écrit un **événement JSON par ligne** sur sa sortie standard pour chaque issue d'un cas d'usage métier (succès, refus, erreur). Le contrat est commun à `shop`, `payment` et `auth` : [log-event.schema.json](log-event.schema.json). La collecte et l'exploitation des logs ne font pas partie de l'application.

## Format

| Champ | Obligatoire | Contenu |
|---|---|---|
| `timestamp` | oui | ISO 8601 UTC à la milliseconde, suffixe `Z` |
| `service` | oui | valeur de `APP_SERVICE_NAME` (`basecamp-shop`, `basecamp-payment`, `basecamp-auth`) |
| `level` | oui | `info` (success), `warning` (denied), `error` (error) |
| `event` | oui | nom stable `<domaine>.<action>`, par exemple `payment.intent_created` |
| `correlation_id` | oui | identifiant de la requête, identique dans tous les services traversés |
| `outcome` | oui | `success`, `denied` (refus métier ou sécurité attendu) ou `error` (défaillance technique) |
| `reason` | si `outcome` ≠ `success` | code stable en `snake_case`, jamais une phrase ni un message d'exception |
| `resource_type`, `resource_id` | si une ressource est ciblée | `product`, `payment_intent`, `order`, `account`… et son identifiant interne |
| `actor_type`, `actor_id` | si connu | `user` + id du compte, ou `service` + nom de l'appelant |
| `duration_ms` | non | durée du cas d'usage |
| `client_ip` | non | adresse du client, réservée aux refus d'`auth` et `payment` (donnée personnelle) |
| `attributes` | non | objet plat de valeurs scalaires non sensibles propres à l'événement |

Exemple :

```json
{"timestamp":"2026-10-20T17:02:40.019Z","service":"basecamp-shop","level":"warning","event":"cart.quote_rejected","correlation_id":"b3a9d7e1-55c4-4d0a-8f21-0c9e4a6d7f33","outcome":"denied","reason":"quantity_out_of_range"}
```

Règles d'évolution : on ajoute des champs optionnels, on ne renomme ni ne supprime jamais un champ ou un `event` publié (des requêtes et des modèles en dépendent).

## Ce qui n'est jamais journalisé

Mot de passe, jeton (JWT, jeton de service, `Authorization`), cookie, clé d'idempotence en clair, numéro de carte, CVV, secret de signature, corps de requête, valeur invalide reçue.

- **Email** : jamais en clair. On journalise `attributes.email_hash`, un HMAC-SHA256 tronqué à 16 caractères hexadécimaux calculé avec `APP_LOG_PSEUDONYM_KEY` (`EmailPseudonymizer`). La même adresse donne toujours la même empreinte tant que la clé ne change pas, sans être réversible.
- **Clé `APP_LOG_PSEUDONYM_KEY`** : obligatoire hors `dev` et `local` (le service refuse de démarrer sans elle). En `dev` et `local`, une clé éphémère est générée : les empreintes changent à chaque démarrage.
- **Filet de sécurité** : l'adaptateur masque la valeur de toute clé d'`attributes` dont un mot est sensible (`password`, `token`, `authorization`, `secret`, `card`, `pan`, `cvv`, `idempotency`, `cookie`, `api_key`…), masque les emails dans les valeurs texte (`[email]`) et les numéros de carte valides (algorithme de Luhn, `[card]`). C'est un dernier recours : le cas d'usage ne doit pas les fournir.

## Corrélation

Un middleware (`app/core/logging/correlation_id_middleware.py`) lit `X-Correlation-ID`. Il le retient seulement s'il respecte `^[A-Za-z0-9-]{8,64}$`, sinon il génère un UUID v4 : un client ne peut pas injecter de contenu libre dans les logs. L'identifiant est stocké dans une variable de contexte, ajouté à chaque événement et renvoyé dans l'en-tête de réponse.

Un appel vers un autre service joint `outbound_headers()` (`app/core/logging/correlation.py`) pour que la même valeur circule.

## Où et comment émettre

- Le **cas d'usage** (`application`) émet l'événement, au succès et à chaque refus, avant de lever l'exception de domaine. Le routeur ne journalise rien.
- Il reçoit le port `BusinessEventLogger` (`app/core/events/`, Python pur, sans dépendance) par son constructeur. La couche `application` est autorisée à importer `app.core.events`, et seulement ce module du cœur.
- L'adaptateur `StructlogBusinessEventLogger` (`app/core/logging/`) est câblé dans `main.py`. Les tests utilisent `InMemoryBusinessEventLogger` (`app/core/__tests__/`).
- Une exception inattendue produit `service.unhandled_error` (`outcome=error`, `reason=internal_error`) et une réponse 500 générique, sans trace ni message. Une requête qui échoue à la validation produit `service.request_rejected` (`denied`, `invalid_request`), sans la valeur reçue.
- Pas de duplication : chaque service garde sa copie du module (aucune bibliothèque partagée), sous `app/core/**`, exclu du calcul de duplication Sonar.

## Règle pour chaque ticket

Tout ticket qui ajoute ou modifie un cas d'usage émet, via le port `BusinessEventLogger`, un événement au succès et à chaque refus, nommés dans le catalogue de `docs/services/<service>.md`. Chaque critère d'acceptation de succès ou de refus a un test unitaire qui vérifie l'événement émis (nom, `outcome`, `reason`, ressource). Un événement n'est jamais renommé après publication. Aucun mot de passe, jeton, clé d'idempotence, numéro de carte ni email en clair.

Critère type à copier dans les tickets : « Journalisation : le cas d'usage émet les événements `<service>.<action>` (succès et refus) du catalogue, vérifiés par test, sans donnée sensible. »

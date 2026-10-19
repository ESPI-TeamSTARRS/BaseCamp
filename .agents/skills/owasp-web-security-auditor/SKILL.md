---
name: owasp-web-security-auditor
description: Audit de sécurité applicative web et API selon l'OWASP Top 10 : détection et remédiation des injections, SSRF, XSS, bris d'authentification et CORS.
category: software-development
---

# OWASP Web Application Security Auditor

Protocole d'audit et de correction pour sécuriser les applications web et API contre le Top 10 OWASP.

## 1. Prévention contre les Injections & XSS

- **Injections SQL** : Bannir formellement la concaténation de chaînes dans les requêtes SQL. Toujours recourir aux paramètres nommés / ORM (ex: SQLAlchemy, Prisma, Drizzle).
- **Injections XSS (Cross-Site Scripting)** :
  - Encoder dynamiquement tout contenu utilisateur injecté dans le DOM.
  - Utiliser `DOMPurify` côté client ou `html.escape()` côté backend.
  - Déployer un header CSP (Content Security Policy) strict :
  `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self';`

## 2. Remédiation Server-Side Request Forgery (SSRF)

Pour toute fonctionnalité prenant une URL en paramètre (webhook, import, proxy) :
```python
import ipaddress
import socket
from urllib.parse import urlparse

BLOCKED_NETWORKS = [
    ipaddress.ip_network('127.0.0.0/8'),
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('169.254.0.0/16'),  # AWS metadata / Link-local
    ipaddress.ip_network('::1/128'),
    ipaddress.ip_network('fc00::/7'),
]

def is_safe_external_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return False
    hostname = parsed.hostname
    if not hostname:
        return False
    try:
        addrinfo = socket.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in addrinfo:
            ip = ipaddress.ip_address(sockaddr[0])
            for blocked in BLOCKED_NETWORKS:
                if ip in blocked:
                    return False
        return True
    except socket.gaierror:
        return False
```

## 3. Sécurité des Sessions et Authentification

- Cookies de session obligatoires : `HttpOnly; Secure; SameSite=Lax`.
- Stockage de mots de passe : `Argon2id` ou `bcrypt` avec facteur de coût adéquat.
- Protection anti-bruteforce : Rate limiting par adresse IP (via header reverse-proxy fiable tel que `CF-Connecting-IP` ou `X-Forwarded-For` vérifié).
- Déconnexion complète : Invalidation côté serveur de la session / token.

---
name: sec-infra-hardening
description: Defensive container & reverse-proxy infrastructure hardening: Docker non-root execution, resource limits (cgroups), Traefik TLS & rate-limit middlewares, Cloudflare origin shielding, and system defense.
category: security
---

# Defensive Infrastructure Hardening (sec-infra-hardening)

Guide de durcissement défensif des conteneurs Docker, du reverse-proxy Traefik et de la passerelle Cloudflare pour un hébergement en production sécurisé.

## 1. Durcissement du Conteneur Dockerfile (Next.js Standalone)

Un conteneur ne doit jamais tourner en `root`. Modèle de Dockerfile sécurisé multi-stage :

```dockerfile
# 1. Utiliser une image minimale alpine ou debian slim officielle
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# 2. Créer un utilisateur et un groupe système sans privilèges
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# 3. Copier uniquement les artefacts nécessaires en assignant la propriété
COPY --chown=nextjs:nodejs public ./public
COPY --chown=nextjs:nodejs .next/standalone ./
COPY --chown=nextjs:nodejs .next/static ./.next/static

# 4. Basculer explicitement sur l'utilisateur non-root
USER nextjs

EXPOSE 3000
CMD ["node", "server.js"]
```

## 2. Durcissement docker-compose.yml (Isolation & Limites de Ressources)

Pour empêcher un déni de service local (épuisement mémoire/CPU de la machine hôte) ou une élévation de privilèges :

```yaml
services:
  app:
    image: caniventure:latest
    restart: unless-stopped
    # 1. Interdiction d'élever les privilèges
    security_opt:
      - no-new-privileges:true
    # 2. Limitation stricte des ressources (cgroups)
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          memory: 128M
    # 3. Système de fichiers root en lecture seule (si les logs vont vers stdout)
    read_only: false # Passer à true si aucun cache disque temporaire n'est requis
    # 4. Déconnexion des capabilities Linux inutiles
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
```

## 3. Configuration Sécurisée du Reverse Proxy Traefik

### A. Middlewares de protection dans Traefik :
- **Rate-Limiting Global** :
  ```yaml
  traefik.http.middlewares.app-ratelimit.ratelimit.average: 100
  traefik.http.middlewares.app-ratelimit.ratelimit.burst: 50
  ```
- **Redirection HTTP vers HTTPS** systématique.
- **TLS Version Min** : Forcer TLS v1.2 ou TLS v1.3 avec cipher suites modernes.

## 4. Protection de l'Origine avec Cloudflare

Pour que l'IP publique du serveur hôte ne soit jamais exposée et que tout le trafic passe par le WAF / DDoS Cloudflare :
1. **Activer le Proxy Cloudflare (Nuage Orange)** sur le DNS `caniventure.tempulse.fr`.
2. **Mode SSL/TLS Cloudflare** : Configurer sur **Full (Strict)** pour vérifier le certificat Let's Encrypt de Traefik de bout en bout.
3. **Restreindre les flux entrants** : Configurer le pare-feu du routeur/serveur pour n'accepter le trafic HTTPS (port 443) que si la requête transite par le proxy Cloudflare (ou via tunnel Cloudflared).

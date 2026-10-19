---
name: micro-interactions-motion
description: Conception de micro-interactions, animations d'interface et états de transition fluides à 60 FPS : courbes d'accélération ergonomiques, skeletons, retours d'actions et micro-animations.
category: creative
---

# Micro-Interactions & Motion Ergonomics Specialist

Guide pour concevoir des animations subtiles, dynamiques et performantes qui renforcent l'expérience utilisateur sans alourdir le rendu.

## 1. Principes de Mouvement Fonctionnel

- **Durée optimale** : Les interactions d'interface doivent être comprises entre **150ms et 350ms**.
  - Micro-interactions (hover, boutons, toggles) : `150ms - 200ms`.
  - Transitions moyennes (modales, volets coulissants, menus) : `250ms - 350ms`.
  - Au-delà de 400ms, l'utilisateur perçoit l'animation comme une lenteur agaçante.
- **Courbes d'accélération naturelles (Easings)** :
  ```css
  /* Entrée d'élément (naturel et réactif) */
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);

  /* Sortie d'élément */
  --ease-in: cubic-bezier(0.4, 0, 1, 1);

  /* Transition interne d'état */
  --ease-in-out: cubic-bezier(0.4, 0, 0.2, 1);
  ```

## 2. Règle des 60 FPS : Propriétés Composées Uniquement

Pour préserver la fluidité absolue sur tous les appareils, n'animer que deux propriétés :
1. `transform` (`translate`, `scale`, `rotate`)
2. `opacity`

**À bannir dans les transitions :** `width`, `height`, `top`, `left`, `margin`, `padding` ou les filtres complexes en boucle (`feGaussianBlur`), qui déclenchent un recalcul complet du layout (reflow) et du repaint.

## 3. États de Chargement : Remplacer les Spinners par des Skeletons

Un spinner attire l'attention sur l'attente. Un skeleton structure la page et donne l'illusion d'un chargement instantané :
```css
.skeleton {
  background: linear-gradient(
    90deg,
    rgba(255, 255, 255, 0.04) 25%,
    rgba(255, 255, 255, 0.10) 50%,
    rgba(255, 255, 255, 0.04) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 6px;
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
```

## 4. Retours Tactiles et Micro-Interactions Clés

- **Bouton d'action réactif** :
  ```css
  .btn-interactive {
    transition: transform 150ms var(--ease-out), box-shadow 150ms var(--ease-out);
  }
  .btn-interactive:hover {
    transform: translateY(-1px);
  }
  .btn-interactive:active {
    transform: translateY(1px) scale(0.98);
  }
  ```
- **Feedback d'action réussie** : Animer subtilement l'icône (changement de couleur ou coche animée) pendant 1.5 seconde avant de revenir à l'état neutre.

from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class LockoutPolicy:
    """Regle de verrouillage, entierement parametrable (aucun seuil en dur dans les etapes).

    - `max_failures` echecs dans `window` verrouillent le sujet;
    - la duree suit l'echelle `durations` : 1er verrou, puis 2e en cas de recidive, etc. La derniere
      duree est le plafond : un attaquant ne peut jamais verrouiller plus longtemps;
    - l'echelle est oubliee apres `memory` sans nouveau verrou (le sujet repart du premier palier).

    Exemples : 5 echecs en 15 min puis 15, 30, 60 min (defaut); un seul nouvel essai puis 5 minutes
    se regle avec `max_failures=2` et `durations=(5 min,)`.
    """

    max_failures: int
    window: timedelta
    durations: tuple[timedelta, ...]
    memory: timedelta

    def __post_init__(self) -> None:
        if self.max_failures < 1:
            raise ValueError("max_failures must be at least 1")
        if self.window <= timedelta(0) or self.memory <= timedelta(0):
            raise ValueError("window and memory must be positive")
        if not self.durations or any(duration <= timedelta(0) for duration in self.durations):
            raise ValueError("durations must hold at least one positive duration")

    def duration_for(self, level: int) -> timedelta:
        """Duree du verrou de rang `level` (1 = premier), plafonnee par le dernier palier."""
        return self.durations[min(level, len(self.durations)) - 1]

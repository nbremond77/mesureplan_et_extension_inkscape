"""Gestion de l'échelle d'une page : cartouche, calibration, contrôle de cohérence.

Principe : une longueur mesurée sur la page (en points PDF) est convertie en
mètres réels par un facteur « mètres par point ».
  - Au cartouche 1:N : facteur = N × 0,0254 / 72 (1 pt = 0,3528 mm papier).
  - Après calibration : facteur = moyenne des (cote réelle / longueur mesurée)
    sur les cotes de référence tracées par l'utilisateur.
Plusieurs références permettent d'estimer la cohérence (dispersion) et de
détecter un PDF déformé ou une cote mal pointée.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field

from mesureplan.geometrie import Point, distance

# Longueur d'un point typographique PDF en mètres (1/72 de pouce)
METRES_PAR_POINT = 0.0254 / 72.0

# Échelles d'architecture courantes : utilisées pour fiabiliser la détection
ECHELLES_USUELLES = {5, 10, 20, 25, 50, 75, 100, 125, 150, 200, 250, 500, 1000, 2000, 2500, 5000}

# « 1/100 », « 1:50 », « 1 / 200 »… sans être collé à d'autres chiffres (dates)
MOTIF_ECHELLE = re.compile(r"(?<![\d/.,])1\s*[/:]\s*(\d{1,4}(?:[.,]\d+)?)(?![\d/])")
# Mots-clés qui, juste avant, confirment qu'il s'agit d'une échelle
MOTS_CLES_ECHELLE = ("ech", "éch", "scale", "echelle", "échelle")


@dataclass
class Reference:
    """Cote de référence : segment tracé sur le plan + longueur réelle connue."""

    p1: Point
    p2: Point
    longueur_reelle_m: float

    @property
    def longueur_pt(self) -> float:
        return distance(self.p1, self.p2)

    @property
    def facteur(self) -> float:
        """Mètres réels par point PDF déduits de cette seule référence."""
        if self.longueur_pt <= 0:
            raise ValueError("Référence de longueur nulle")
        return self.longueur_reelle_m / self.longueur_pt

    def vers_dict(self) -> dict:
        return {"p1": list(self.p1), "p2": list(self.p2), "longueur_reelle_m": self.longueur_reelle_m}

    @classmethod
    def depuis_dict(cls, d: dict) -> "Reference":
        return cls(tuple(d["p1"]), tuple(d["p2"]), float(d["longueur_reelle_m"]))


@dataclass
class EchellePage:
    """Échelle d'une page : valeur du cartouche + éventuelles références de calibration."""

    denominateur_cartouche: float = 100.0
    origine_cartouche: str = "défaut"  # "défaut", "lue sur le plan", "saisie"
    references: list[Reference] = field(default_factory=list)

    # --- Facteurs ----------------------------------------------------------
    @property
    def facteur_cartouche(self) -> float:
        return METRES_PAR_POINT * self.denominateur_cartouche

    @property
    def est_calibree(self) -> bool:
        return bool(self.references)

    @property
    def facteur(self) -> float:
        """Facteur effectivement utilisé pour les mesures (m / pt)."""
        if self.references:
            return statistics.fmean(r.facteur for r in self.references)
        return self.facteur_cartouche

    @property
    def denominateur_effectif(self) -> float:
        """Échelle réellement appliquée, exprimée en 1:N."""
        return self.facteur / METRES_PAR_POINT

    @property
    def ecart_cartouche_pct(self) -> float | None:
        """Écart de l'échelle calibrée par rapport au cartouche (en %)."""
        if not self.references:
            return None
        return (self.facteur / self.facteur_cartouche - 1.0) * 100.0

    @property
    def dispersion_pct(self) -> float | None:
        """Étendue relative des facteurs des références (max-min)/moyenne, en %."""
        if len(self.references) < 2:
            return None
        facteurs = [r.facteur for r in self.references]
        return (max(facteurs) - min(facteurs)) / statistics.fmean(facteurs) * 100.0

    @property
    def libelle_source(self) -> str:
        if self.references:
            n = len(self.references)
            return f"calibrée sur {n} cote{'s' if n > 1 else ''}"
        return f"cartouche ({self.origine_cartouche})"

    # --- Conversions -------------------------------------------------------
    def longueur_m(self, longueur_pt: float) -> float:
        return longueur_pt * self.facteur

    def surface_m2(self, surface_pt2: float) -> float:
        return surface_pt2 * self.facteur ** 2

    # --- Persistance -------------------------------------------------------
    def vers_dict(self) -> dict:
        return {
            "denominateur_cartouche": self.denominateur_cartouche,
            "origine_cartouche": self.origine_cartouche,
            "references": [r.vers_dict() for r in self.references],
        }

    @classmethod
    def depuis_dict(cls, d: dict) -> "EchellePage":
        return cls(
            denominateur_cartouche=float(d.get("denominateur_cartouche", 100.0)),
            origine_cartouche=str(d.get("origine_cartouche", "saisie")),
            references=[Reference.depuis_dict(r) for r in d.get("references", [])],
        )


def analyser_texte_echelle(texte: str) -> str:
    """Normalise une saisie « 1:100 », « 1/100 », « 100 » → dénominateur sous forme de texte."""
    brut = texte.strip().replace(" ", "")
    m = re.fullmatch(r"(?:1[:/])?(\d+(?:[.,]\d+)?)", brut)
    if not m:
        raise ValueError(f"Échelle non reconnue : « {texte} » (attendu 1:100, 1/100 ou 100)")
    return m.group(1).replace(",", ".")


def lire_denominateur(texte: str) -> float:
    """Convertit une saisie utilisateur en dénominateur strictement positif."""
    valeur = float(analyser_texte_echelle(texte))
    if valeur <= 0:
        raise ValueError("Le dénominateur d'échelle doit être positif")
    return valeur


@dataclass(frozen=True)
class DetectionEchelle:
    """Échelle trouvée dans le texte de la page."""

    denominateur: float
    occurrences: int
    confirmee_par_mot_cle: bool
    autres: tuple[float, ...]  # autres échelles présentes (ex. détails au 1:20)


def detecter_echelle(texte: str) -> DetectionEchelle | None:
    """Recherche la mention d'échelle la plus probable dans le texte extrait du PDF.

    Hypothèse (à vérifier par calibration) : l'échelle principale est celle qui
    est précédée d'un mot-clé (« Éch. », « Échelle », « Scale ») ou, à défaut,
    l'échelle usuelle la plus fréquente.
    """
    scores: Counter[float] = Counter()
    confirmees: set[float] = set()
    for m in MOTIF_ECHELLE.finditer(texte):
        try:
            denominateur = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        contexte = texte[max(0, m.start() - 20): m.start()].lower()
        a_mot_cle = any(mot in contexte for mot in MOTS_CLES_ECHELLE)
        usuelle = denominateur in ECHELLES_USUELLES
        if not (a_mot_cle or usuelle):
            continue  # probablement une fraction ou une numérotation
        scores[denominateur] += 3 if a_mot_cle else 1
        if a_mot_cle:
            confirmees.add(denominateur)
    if not scores:
        return None
    meilleur, _score = scores.most_common(1)[0]
    occurrences = len([m for m in MOTIF_ECHELLE.finditer(texte)
                       if _valeur_ou_none(m.group(1)) == meilleur])
    autres = tuple(sorted(d for d in scores if d != meilleur))
    return DetectionEchelle(meilleur, occurrences, meilleur in confirmees, autres)


def _valeur_ou_none(texte: str) -> float | None:
    try:
        return float(texte.replace(",", "."))
    except ValueError:
        return None

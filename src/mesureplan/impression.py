"""Mise en page d'une impression à l'échelle (calculs purs, testables).

Principe : une longueur de la page source (pt PDF) vaut « facteur » mètres
réels (échelle calibrée de la page). À l'échelle d'impression 1:N, elle doit
mesurer facteur / N mètres sur le papier, soit un agrandissement
k = facteur / (N × 0,3528 mm) en points de sortie par point source.

Si la zone ne tient pas sur une feuille, elle est découpée en mosaïque avec
un recouvrement (bande commune entre feuilles voisines) pour l'assemblage.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from mesureplan.echelle import METRES_PAR_POINT

PT_PAR_MM = 72.0 / 25.4

# Formats en mm, portrait (largeur, hauteur)
FORMATS_PAPIER: dict[str, tuple[float, float]] = {
    "A4": (210.0, 297.0),
    "A3": (297.0, 420.0),
    "A2": (420.0, 594.0),
    "A1": (594.0, 841.0),
    "A0": (841.0, 1189.0),
    "Letter (US)": (215.9, 279.4),
    "Tabloid (US)": (279.4, 431.8),
}
ORIENTATIONS = ("auto", "portrait", "paysage")
LONGUEURS_BARRE_M = (0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000)


def facteur_agrandissement(metres_par_pt: float, denominateur_impression: float) -> float:
    """k : points de sortie par point source pour imprimer à 1:N."""
    if denominateur_impression <= 0:
        raise ValueError("Échelle d'impression invalide")
    return metres_par_pt / (denominateur_impression * METRES_PAR_POINT)


@dataclass(frozen=True)
class Tuile:
    """Une feuille de la mosaïque."""

    ligne: int
    colonne: int
    source: tuple[float, float, float, float]       # zone du plan (pt source)
    destination: tuple[float, float, float, float]  # emplacement sur la feuille (pt sortie)


@dataclass
class PlanImpression:
    """Résultat de la mise en page."""

    format: str
    orientation: str
    largeur_feuille: float   # pt
    hauteur_feuille: float   # pt
    marge: float             # pt
    pied: float              # pt réservés en bas pour la légende et la barre d'échelle
    recouvrement: float      # pt
    k: float
    denominateur: float
    zone: tuple[float, float, float, float]
    lignes: int
    colonnes: int
    tuiles: list[Tuile] = field(default_factory=list)

    @property
    def nombre_feuilles(self) -> int:
        return self.lignes * self.colonnes

    @property
    def taille_imprimee_mm(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.zone
        return ((x1 - x0) * self.k / PT_PAR_MM, (y1 - y0) * self.k / PT_PAR_MM)

    @property
    def zone_utile(self) -> tuple[float, float, float, float]:
        """Rectangle imprimable d'une feuille (pt sortie), hors marges et pied."""
        return (self.marge, self.marge, self.largeur_feuille - self.marge,
                self.hauteur_feuille - self.marge - self.pied)


def _nombre_feuilles(taille: float, utile: float, recouvrement: float) -> int:
    if taille <= utile + 1e-6:
        return 1
    return math.ceil((taille - recouvrement) / (utile - recouvrement) - 1e-9)


def _intervalles(taille: float, utile: float, recouvrement: float, n: int) -> list[tuple[float, float]]:
    """Découpe [0, taille] en n intervalles de longueur ≤ utile se chevauchant de « recouvrement »."""
    if n == 1:
        return [(0.0, taille)]
    pas = utile - recouvrement
    return [(i * pas, min(i * pas + utile, taille)) for i in range(n)]


def planifier(zone: tuple[float, float, float, float], k: float, format_mm: tuple[float, float],
              nom_format: str = "", orientation: str = "auto", marge_mm: float = 10.0,
              recouvrement_mm: float = 10.0, pied_mm: float = 14.0,
              denominateur: float = 0.0) -> PlanImpression:
    """Calcule l'orientation (si « auto ») et la mosaïque minimisant le nombre de feuilles."""
    if orientation not in ORIENTATIONS:
        raise ValueError(f"Orientation inconnue : {orientation}")
    x0, y0, x1, y1 = zone
    largeur_z, hauteur_z = (x1 - x0) * k, (y1 - y0) * k
    if largeur_z <= 0 or hauteur_z <= 0:
        raise ValueError("Zone à imprimer vide")
    marge, pied, recouvrement = marge_mm * PT_PAR_MM, pied_mm * PT_PAR_MM, recouvrement_mm * PT_PAR_MM

    candidats = []
    petit, grand = sorted(format_mm)
    for nom_orientation, (lw, lh) in (("portrait", (petit, grand)), ("paysage", (grand, petit))):
        if orientation != "auto" and orientation != nom_orientation:
            continue
        lw, lh = lw * PT_PAR_MM, lh * PT_PAR_MM
        utile_l, utile_h = lw - 2 * marge, lh - 2 * marge - pied
        if utile_l <= recouvrement * 2 or utile_h <= recouvrement * 2:
            raise ValueError("Marges ou recouvrement trop grands pour ce format de papier")
        colonnes = _nombre_feuilles(largeur_z, utile_l, recouvrement)
        lignes = _nombre_feuilles(hauteur_z, utile_h, recouvrement)
        # Critère : nombre de feuilles, puis surface de papier perdue
        perte = colonnes * utile_l * lignes * utile_h - largeur_z * hauteur_z
        candidats.append((colonnes * lignes, perte, nom_orientation, lw, lh, utile_l, utile_h, colonnes, lignes))
    _n, _perte, nom_orientation, lw, lh, utile_l, utile_h, colonnes, lignes = min(candidats)

    plan = PlanImpression(nom_format, nom_orientation, lw, lh, marge, pied, recouvrement, k, denominateur, zone,
                          lignes, colonnes)
    for i, (a_y, b_y) in enumerate(_intervalles(hauteur_z, utile_h, recouvrement, lignes)):
        for j, (a_x, b_x) in enumerate(_intervalles(largeur_z, utile_l, recouvrement, colonnes)):
            # Une seule feuille dans un sens : dessin centré dans la zone utile
            dx = marge + ((utile_l - largeur_z) / 2 if colonnes == 1 else 0.0)
            dy = marge + ((utile_h - hauteur_z) / 2 if lignes == 1 else 0.0)
            source = (x0 + a_x / k, y0 + a_y / k, x0 + b_x / k, y0 + b_y / k)
            destination = (dx, dy, dx + (b_x - a_x), dy + (b_y - a_y))
            plan.tuiles.append(Tuile(i, j, source, destination))
    return plan


def barre_echelle(denominateur: float, longueur_max_mm: float = 80.0) -> tuple[float, int, float]:
    """Barre d'échelle « ronde » : (longueur réelle m, nombre de divisions, longueur papier mm)."""
    retenue = LONGUEURS_BARRE_M[0]
    for longueur in LONGUEURS_BARRE_M:
        if longueur * 1000.0 / denominateur <= longueur_max_mm:
            retenue = longueur
    chiffre = f"{retenue:g}".lstrip("0.").lstrip("0")[:1]
    divisions = 4 if chiffre == "2" else 5
    return retenue, divisions, retenue * 1000.0 / denominateur


def nom_tuile(t: Tuile) -> str:
    """Repère de feuille lisible : A1, A2… (lettre = ligne, chiffre = colonne)."""
    lettres = ""
    n = t.ligne
    while True:
        lettres = chr(ord("A") + n % 26) + lettres
        n = n // 26 - 1
        if n < 0:
            break
    return f"{lettres}{t.colonne + 1}"

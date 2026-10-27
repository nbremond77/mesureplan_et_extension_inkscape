"""Noyau de calcul 3D de l'extension Blender « MesurePlan 3D » (aucune dépendance à bpy).

Toutes les fonctions travaillent sur des tuples (x, y, z). Les points reçus
sont déjà convertis en mètres réels par la couche Blender :
    point_m = point_monde (unités Blender) × échelle de la scène × facteur de calibration.
Les composantes ΔX, ΔY, ΔZ sont exprimées dans un repère choisi : le repère
global de la scène, ou celui d'un objet de référence (matrice de rotation
« monde → repère » fournie par la couche Blender).
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

Vecteur = tuple[float, float, float]
Point2D = tuple[float, float]
Matrice3 = tuple[Vecteur, Vecteur, Vecteur]   # lignes d'une matrice 3×3

EPSILON = 1e-12

# Types de mesure (valeurs stockées dans le fichier .blend : ne pas les renommer)
DISTANCE = "DISTANCE"
DISTANCE_XYZ = "DISTANCE_XYZ"
CHAINE = "CHAINE"
SURFACE = "SURFACE"
ANGLE = "ANGLE"
CALIBRATION = "CALIBRATION"

# Nombre de points : fixe (terminaison automatique) ou minimum (terminaison manuelle)
POINTS_FIXES = {DISTANCE: 2, DISTANCE_XYZ: 2, ANGLE: 3, CALIBRATION: 2}
POINTS_MINIMUM = {CHAINE: 2, SURFACE: 3}

LIBELLES = {DISTANCE: "Distance", DISTANCE_XYZ: "Distance XYZ", CHAINE: "Chaîne",
            SURFACE: "Surface", ANGLE: "Angle", CALIBRATION: "Calibration"}


# ---------------------------------------------------------------------------
# Algèbre vectorielle élémentaire
# ---------------------------------------------------------------------------

def ajouter(a: Vecteur, b: Vecteur) -> Vecteur:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def soustraire(a: Vecteur, b: Vecteur) -> Vecteur:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def multiplier(v: Vecteur, k: float) -> Vecteur:
    return (v[0] * k, v[1] * k, v[2] * k)


def produit_scalaire(a: Vecteur, b: Vecteur) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def produit_vectoriel(a: Vecteur, b: Vecteur) -> Vecteur:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norme(v: Vecteur) -> float:
    return math.sqrt(produit_scalaire(v, v))


def distance(a: Vecteur, b: Vecteur) -> float:
    return norme(soustraire(b, a))


def milieu(a: Vecteur, b: Vecteur) -> Vecteur:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)


def appliquer(rotation: Matrice3 | None, v: Vecteur) -> Vecteur:
    """Produit matrice × vecteur ; sans matrice, le vecteur est rendu tel quel (repère global)."""
    if rotation is None:
        return v
    return tuple(produit_scalaire(ligne, v) for ligne in rotation)  # type: ignore[return-value]


def centroide(points: Sequence[Vecteur]) -> Vecteur:
    n = max(len(points), 1)
    return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n, sum(p[2] for p in points) / n)


# ---------------------------------------------------------------------------
# Mesures
# ---------------------------------------------------------------------------

def composantes(a: Vecteur, b: Vecteur, rotation: Matrice3 | None = None) -> dict[str, float | None]:
    """Décomposition de a→b dans le repère choisi.

    Retourne : longueur, dx, dy, dz (signés), horizontale (longueur projetée sur le plan XY du
    repère), pente_deg (angle avec ce plan, 0 à 90°), pente_pct (|ΔZ| / horizontale × 100,
    None si la mesure est verticale), angle_plan (angle aigu de la projection XY avec l'axe X).
    """
    d = appliquer(rotation, soustraire(b, a))
    horizontale = math.hypot(d[0], d[1])
    longueur = norme(d)
    pente_deg = math.degrees(math.atan2(abs(d[2]), horizontale)) if longueur > EPSILON else 0.0
    pente_pct = abs(d[2]) / horizontale * 100.0 if horizontale > EPSILON else None
    angle_plan = math.degrees(math.atan2(abs(d[1]), abs(d[0]))) if horizontale > EPSILON else 0.0
    return {"longueur": longueur, "dx": d[0], "dy": d[1], "dz": d[2], "horizontale": horizontale,
            "pente_deg": pente_deg, "pente_pct": pente_pct, "angle_plan": angle_plan}


def points_decomposition(a: Vecteur, b: Vecteur, rotation: Matrice3 | None = None) -> list[Vecteur]:
    """Chemin a → +ΔX → +ΔY → +ΔZ = b (coordonnées monde), pour dessiner les trois composantes.

    Les axes du repère, exprimés dans le monde, sont les LIGNES de la matrice monde → repère
    (matrice orthonormée : son inverse est sa transposée).
    """
    dx, dy, dz = appliquer(rotation, soustraire(b, a))
    axes = rotation if rotation is not None else ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    p1 = ajouter(a, multiplier(axes[0], dx))
    p2 = ajouter(p1, multiplier(axes[1], dy))
    return [a, p1, p2, b]


def longueur_polyligne(points: Sequence[Vecteur], fermee: bool = False) -> float:
    if len(points) < 2:
        return 0.0
    total = sum(distance(points[i], points[i + 1]) for i in range(len(points) - 1))
    if fermee and len(points) > 2:
        total += distance(points[-1], points[0])
    return total


def normale_newell(points: Sequence[Vecteur]) -> Vecteur:
    """Normale de Newell : sa norme vaut 2 × l'aire du polygone (exacte s'il est plan)."""
    nx = ny = nz = 0.0
    n = len(points)
    for i in range(n):
        x1, y1, z1 = points[i]
        x2, y2, z2 = points[(i + 1) % n]
        nx += (y1 - y2) * (z1 + z2)
        ny += (z1 - z2) * (x1 + x2)
        nz += (x1 - x2) * (y1 + y2)
    return (nx, ny, nz)


def surface(points: Sequence[Vecteur], rotation: Matrice3 | None = None) -> dict[str, float]:
    """Surface d'un polygone 3D : aire vraie, aire projetée sur le plan XY du repère, périmètre,
    pente du plan (0° = horizontal, 90° = vertical) et défaut de planéité (écart maximal au plan moyen).
    """
    if len(points) < 3:
        return {"surface": 0.0, "surface_xy": 0.0, "perimetre": longueur_polyligne(points, True),
                "pente_deg": 0.0, "planeite": 0.0}
    locaux = [appliquer(rotation, p) for p in points]
    normale = normale_newell(locaux)
    double_aire = norme(normale)
    aire = double_aire / 2.0
    aire_xy = abs(normale[2]) / 2.0
    if double_aire > EPSILON:
        unitaire = multiplier(normale, 1.0 / double_aire)
        pente = math.degrees(math.acos(min(1.0, abs(unitaire[2]))))
        c = centroide(locaux)
        planeite = max(abs(produit_scalaire(soustraire(p, c), unitaire)) for p in locaux)
    else:
        pente, planeite = 0.0, 0.0
    return {"surface": aire, "surface_xy": aire_xy, "perimetre": longueur_polyligne(points, True),
            "pente_deg": pente, "planeite": planeite}


def angle_trois_points(a: Vecteur, sommet: Vecteur, b: Vecteur) -> float:
    """Angle en degrés (0 à 180) entre les bras sommet→a et sommet→b, dans l'espace."""
    u, v = soustraire(a, sommet), soustraire(b, sommet)
    nu, nv = norme(u), norme(v)
    if nu < EPSILON or nv < EPSILON:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, produit_scalaire(u, v) / (nu * nv)))))


def valeurs(type_mesure: str, points: Sequence[Vecteur], rotation: Matrice3 | None = None) -> dict:
    """Toutes les valeurs d'une mesure (points en mètres)."""
    pts = list(points)
    if type_mesure in (DISTANCE, CALIBRATION):
        return {"longueur": distance(pts[0], pts[-1])}
    if type_mesure == DISTANCE_XYZ:
        return composantes(pts[0], pts[-1], rotation)
    if type_mesure == CHAINE:
        locaux = [appliquer(rotation, p) for p in pts]
        horizontale = sum(math.hypot(locaux[i + 1][0] - locaux[i][0], locaux[i + 1][1] - locaux[i][1])
                          for i in range(len(locaux) - 1))
        return {"longueur": longueur_polyligne(pts), "horizontale": horizontale,
                "dz": locaux[-1][2] - locaux[0][2]}
    if type_mesure == SURFACE:
        return surface(pts, rotation)
    if type_mesure == ANGLE:
        return {"angle": angle_trois_points(*pts[:3])}
    raise ValueError(f"Type de mesure inconnu : {type_mesure}")


def mettre_a_l_echelle(points: Iterable[Vecteur], pivot: Vecteur, facteur: float) -> list[Vecteur]:
    """Homothétie de centre « pivot » (utilisée quand la calibration est appliquée aux objets)."""
    return [ajouter(pivot, multiplier(soustraire(p, pivot), facteur)) for p in points]


# ---------------------------------------------------------------------------
# Écran : accrochage et pointillés (coordonnées en pixels)
# ---------------------------------------------------------------------------

# Priorité d'accrochage à distance égale : les points remarquables d'abord
PRIORITE = {"sommet": 0, "mesure": 0, "milieu": 1, "arête": 2, "face": 3, "libre": 4}


@dataclass(frozen=True)
class Candidat:
    """Point candidat à l'accrochage : position écran, position 3D (monde), nature."""

    ecran: Point2D
    monde: Vecteur
    nature: str


def choisir_accrochage(curseur: Point2D, candidats: Iterable[Candidat], tolerance_px: float) -> Candidat | None:
    """Règle d'accrochage (identique à l'application 2D) :
    1. point remarquable (sommet, point de mesure, milieu) le plus proche dans la tolérance ;
    2. sinon, point sur arête le plus proche dans la tolérance ;
    3. sinon, point touché sur la face sous le curseur ;
    4. sinon, rien (la couche Blender place alors un point libre).
    """
    ponctuels, aretes, faces = [], [], []
    for c in candidats:
        d = math.hypot(c.ecran[0] - curseur[0], c.ecran[1] - curseur[1])
        if c.nature == "face":
            faces.append((d, c))
        elif d <= tolerance_px:
            (aretes if c.nature == "arête" else ponctuels).append((PRIORITE.get(c.nature, 9), d, c))
    if ponctuels:
        # À distance quasi égale (moins de 1 px), un sommet l'emporte sur un milieu
        return min(ponctuels, key=lambda r: (round(r[1]), r[0], r[1]))[2]
    if aretes:
        return min(aretes, key=lambda r: r[1])[2]
    if faces:
        return min(faces, key=lambda r: r[0])[1]
    return None


def projection_segment_2d(p: Point2D, a: Point2D, b: Point2D) -> tuple[Point2D, float]:
    """Projeté de p sur [a, b] (borné) et paramètre t ∈ [0, 1]."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    if l2 < EPSILON:
        return a, 0.0
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
    return (a[0] + t * dx, a[1] + t * dy), t


def segments_pointilles(a: Point2D, b: Point2D, tiret: float = 6.0, espace: float = 4.0) -> list[Point2D]:
    """Extrémités des tirets d'une ligne pointillée (liste plate de paires, pour un tracé 'LINES')."""
    longueur = math.hypot(b[0] - a[0], b[1] - a[1])
    if longueur < EPSILON:
        return []
    ux, uy = (b[0] - a[0]) / longueur, (b[1] - a[1]) / longueur
    points: list[Point2D] = []
    s = 0.0
    while s < longueur:
        fin = min(s + tiret, longueur)
        points += [(a[0] + ux * s, a[1] + uy * s), (a[0] + ux * fin, a[1] + uy * fin)]
        s += tiret + espace
    return points


# ---------------------------------------------------------------------------
# Mise en forme (convention française) et étiquettes
# ---------------------------------------------------------------------------

FACTEURS_UNITE = {"m": 1.0, "cm": 100.0, "mm": 1000.0}


def formater_nombre(valeur: float, decimales: int) -> str:
    """1234.5 → « 1 234,50 » (espace fine insécable pour les milliers)."""
    return f"{valeur:,.{decimales}f}".replace(",", " ").replace(".", ",")


@dataclass
class Formateur:
    unite: str = "m"
    decimales: dict[str, int] = field(default_factory=lambda: {"m": 2, "cm": 1, "mm": 0})
    decimales_surface: int = 2
    decimales_angle: int = 1

    def longueur(self, metres: float, signe: bool = False) -> str:
        texte = formater_nombre(metres * FACTEURS_UNITE[self.unite], self.decimales.get(self.unite, 2))
        if signe and metres > 0:
            texte = "+" + texte
        return f"{texte} {self.unite}"

    def surface(self, m2: float) -> str:
        return f"{formater_nombre(m2, self.decimales_surface)} m²"

    def angle(self, degres: float) -> str:
        return f"{formater_nombre(degres, self.decimales_angle)}°"

    def pente(self, pourcentage: float | None) -> str:
        return "verticale" if pourcentage is None else f"{formater_nombre(pourcentage, 1)} %"


@dataclass
class Etiquettes:
    """Textes à afficher : étiquette principale (au milieu) et étiquettes des composantes ΔX, ΔY, ΔZ."""

    principale: str
    composantes: tuple[str, str, str] | None = None


def etiquettes(type_mesure: str, v: dict, fmt: Formateur, nom: str = "") -> Etiquettes:
    """Textes affichés dans la vue 3D pour une mesure."""
    if type_mesure == DISTANCE_XYZ:
        lignes = [f"L {fmt.longueur(v['longueur'])}",
                  f"Horiz. {fmt.longueur(v['horizontale'])} · pente {fmt.angle(v['pente_deg'])}"]
        legs = (f"ΔX {fmt.longueur(abs(v['dx']))}", f"ΔY {fmt.longueur(abs(v['dy']))}",
                f"ΔZ {fmt.longueur(abs(v['dz']))}")
    elif type_mesure == CHAINE:
        lignes = [f"Σ {fmt.longueur(v['longueur'])}",
                  f"Σ horiz. {fmt.longueur(v['horizontale'])} · ΔZ {fmt.longueur(v['dz'], signe=True)}"]
        legs = None
    elif type_mesure == SURFACE:
        lignes = [f"S {fmt.surface(v['surface'])}", f"Proj. XY {fmt.surface(v['surface_xy'])}",
                  f"P {fmt.longueur(v['perimetre'])} · pente {fmt.angle(v['pente_deg'])}"]
        legs = None
    elif type_mesure == ANGLE:
        lignes, legs = [fmt.angle(v["angle"])], None
    else:
        lignes, legs = [fmt.longueur(v["longueur"])], None
    if nom:
        lignes.insert(0, nom)
    return Etiquettes("\n".join(lignes), legs)


def detail(type_mesure: str, v: dict, fmt: Formateur, tolerance_planeite_m: float = 0.005) -> list[str]:
    """Lignes du panneau « détail » (toutes les valeurs, signées)."""
    if type_mesure == DISTANCE_XYZ:
        return [f"Longueur : {fmt.longueur(v['longueur'])}",
                f"ΔX : {fmt.longueur(v['dx'], signe=True)}",
                f"ΔY : {fmt.longueur(v['dy'], signe=True)}",
                f"ΔZ : {fmt.longueur(v['dz'], signe=True)}",
                f"Horizontale : {fmt.longueur(v['horizontale'])}",
                f"Pente : {fmt.angle(v['pente_deg'])} ({fmt.pente(v['pente_pct'])})",
                f"Angle en plan / X : {fmt.angle(v['angle_plan'])}"]
    if type_mesure == SURFACE:
        lignes = [f"Surface vraie : {fmt.surface(v['surface'])}",
                  f"Surface projetée XY : {fmt.surface(v['surface_xy'])}",
                  f"Périmètre : {fmt.longueur(v['perimetre'])}",
                  f"Pente du plan : {fmt.angle(v['pente_deg'])}"]
        if v["planeite"] > tolerance_planeite_m:
            lignes.append(f"⚠ Non plane : écart {fmt.longueur(v['planeite'])}")
        return lignes
    if type_mesure == CHAINE:
        return [f"Longueur : {fmt.longueur(v['longueur'])}",
                f"Longueur horizontale : {fmt.longueur(v['horizontale'])}",
                f"Dénivelé début → fin : {fmt.longueur(v['dz'], signe=True)}"]
    if type_mesure == ANGLE:
        return [f"Angle : {fmt.angle(v['angle'])}"]
    return [f"Longueur : {fmt.longueur(v['longueur'])}"]


def valeur_principale(type_mesure: str, v: dict, fmt: Formateur) -> str:
    if type_mesure == SURFACE:
        return fmt.surface(v["surface"])
    if type_mesure == ANGLE:
        return fmt.angle(v["angle"])
    return fmt.longueur(v["longueur"])


# ---------------------------------------------------------------------------
# Export CSV
# ---------------------------------------------------------------------------

COLONNES_CSV = ["Nom", "Type", "Longueur (m)", "ΔX (m)", "ΔY (m)", "ΔZ (m)", "Horizontale (m)",
                "Pente (°)", "Pente (%)", "Surface (m²)", "Surface XY (m²)", "Périmètre (m)",
                "Angle (°)", "Planéité (m)", "Repère", "Points (m)"]
CLES_CSV = ["longueur", "dx", "dy", "dz", "horizontale", "pente_deg", "pente_pct", "surface", "surface_xy",
            "perimetre", "angle", "planeite"]


def exporter_csv(chemin: Path, mesures: Iterable[tuple[str, str, dict, list[Vecteur]]], repere: str,
                 separateur: str = ";", separateur_decimal: str = ",") -> int:
    """Écrit les mesures (nom, type, valeurs, points en m) ; valeurs en unités SI, signées."""
    def nombre(x: float | None, d: int = 4) -> str:
        return "" if x is None else f"{x:.{d}f}".replace(".", separateur_decimal)

    n = 0
    with Path(chemin).open("w", encoding="utf-8-sig", newline="") as flux:
        ecrivain = csv.writer(flux, delimiter=separateur)
        ecrivain.writerow(COLONNES_CSV)
        for nom, type_mesure, v, points in mesures:
            ecrivain.writerow([nom, LIBELLES.get(type_mesure, type_mesure)]
                              + [nombre(v.get(cle), 2 if cle in ("pente_deg", "pente_pct", "angle") else 4)
                                 for cle in CLES_CSV]
                              + [repere, " ".join("{:.4f},{:.4f},{:.4f}".format(*p) for p in points)])
            n += 1
    return n

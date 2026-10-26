"""Géométrie plane pure (sans dépendance graphique), testable isolément.

Toutes les coordonnées sont exprimées dans le repère de la page PDF,
en points typographiques (1 pt = 1/72 pouce), axe Y vers le bas.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Sequence

Point = tuple[float, float]

# Drapeaux décrivant la nature d'un segment extrait du PDF
EXTREMITE_A = 1      # le point a est une vraie extrémité de trait
EXTREMITE_B = 2      # le point b est une vraie extrémité de trait
SEGMENT_DROIT = 4    # segment rectiligne (son milieu a un sens)
SEGMENT_COMPLET = EXTREMITE_A | EXTREMITE_B | SEGMENT_DROIT

EPSILON = 1e-9


# ---------------------------------------------------------------------------
# Mesures élémentaires
# ---------------------------------------------------------------------------

def distance(a: Point, b: Point) -> float:
    """Distance euclidienne entre deux points."""
    return math.hypot(b[0] - a[0], b[1] - a[1])


def longueur_polyligne(points: Sequence[Point], fermee: bool = False) -> float:
    """Somme des longueurs des segments ; ajoute le segment de fermeture si demandé."""
    if len(points) < 2:
        return 0.0
    total = sum(distance(points[i], points[i + 1]) for i in range(len(points) - 1))
    if fermee and len(points) > 2:
        total += distance(points[-1], points[0])
    return total


def aire_signee(points: Sequence[Point]) -> float:
    """Aire signée par la formule du lacet (Gauss)."""
    if len(points) < 3:
        return 0.0
    somme = 0.0
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        somme += x1 * y2 - x2 * y1
    return somme / 2.0


def aire_polygone(points: Sequence[Point]) -> float:
    """Aire (positive) d'un polygone simple."""
    return abs(aire_signee(points))


def centroide_polygone(points: Sequence[Point]) -> Point:
    """Centre de gravité d'un polygone ; moyenne des sommets si l'aire est nulle."""
    a = aire_signee(points)
    if abs(a) < EPSILON:
        n = max(len(points), 1)
        return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n)
    cx = cy = 0.0
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        facteur = x1 * y2 - x2 * y1
        cx += (x1 + x2) * facteur
        cy += (y1 + y2) * facteur
    return (cx / (6.0 * a), cy / (6.0 * a))


def polygone_auto_intersecte(points: Sequence[Point]) -> bool:
    """Vrai si deux côtés non adjacents se croisent (l'aire calculée serait fausse)."""
    n = len(points)
    if n < 4:
        return False
    cotes = [(points[i], points[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        for j in range(i + 2, n):
            # Les côtés i et j sont adjacents s'ils partagent un sommet (cas premier/dernier)
            if i == 0 and j == n - 1:
                continue
            if intersection_segments(*cotes[i], *cotes[j]) is not None:
                return True
    return False


def angle_trois_points(a: Point, sommet: Point, b: Point) -> float:
    """Angle géométrique en degrés (0 à 180) entre les bras sommet→a et sommet→b."""
    v1 = (a[0] - sommet[0], a[1] - sommet[1])
    v2 = (b[0] - sommet[0], b[1] - sommet[1])
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if n1 < EPSILON or n2 < EPSILON:
        return 0.0
    cosinus = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
    # Bornage contre les erreurs d'arrondi avant acos
    return math.degrees(math.acos(max(-1.0, min(1.0, cosinus))))


def orientation_degres(origine: Point, p: Point) -> float:
    """Orientation d'un vecteur en degrés, sens trigonométrique écran (Y vers le bas inversé)."""
    return math.degrees(math.atan2(-(p[1] - origine[1]), p[0] - origine[0]))


def tourner(p: Point, centre: Point, angle_degres: float) -> Point:
    """Rotation de p autour de centre, angle positif = sens trigonométrique À L'ÉCRAN (Y vers le bas)."""
    a = math.radians(angle_degres)
    dx, dy = p[0] - centre[0], p[1] - centre[1]
    return (centre[0] + dx * math.cos(a) + dy * math.sin(a), centre[1] - dx * math.sin(a) + dy * math.cos(a))


def composantes(a: Point, b: Point) -> tuple[float, float, float, float]:
    """Décomposition du vecteur a→b : (ΔX, ΔY, angle aigu / horizontale, orientation).

    ΔX positif vers la droite, ΔY positif VERS LE HAUT (convention des plans, alors que
    le repère PDF a l'axe Y vers le bas). L'angle aigu (0 à 90°) ne dépend pas de l'ordre
    des clics ; l'orientation (]-180 ; 180]) est celle du vecteur a→b, sens trigonométrique.
    """
    dx = b[0] - a[0]
    dy = -(b[1] - a[1])
    angle_aigu = math.degrees(math.atan2(abs(dy), abs(dx))) if (dx or dy) else 0.0
    return dx, dy, angle_aigu, math.degrees(math.atan2(dy, dx)) if (dx or dy) else 0.0


def milieu(a: Point, b: Point) -> Point:
    """Milieu d'un segment."""
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def projection_sur_segment(p: Point, a: Point, b: Point) -> tuple[Point, float]:
    """Projeté orthogonal de p sur [a, b] (borné aux extrémités) et paramètre t ∈ [0, 1]."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    longueur2 = dx * dx + dy * dy
    if longueur2 < EPSILON:
        return a, 0.0
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / longueur2
    t = max(0.0, min(1.0, t))
    return (a[0] + t * dx, a[1] + t * dy), t


def intersection_segments(a: Point, b: Point, c: Point, d: Point) -> Point | None:
    """Point d'intersection des segments [a,b] et [c,d], ou None (parallèles / disjoints)."""
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    denominateur = r[0] * s[1] - r[1] * s[0]
    if abs(denominateur) < EPSILON:
        return None  # parallèles ou colinéaires : pas de point unique
    q = (c[0] - a[0], c[1] - a[1])
    t = (q[0] * s[1] - q[1] * s[0]) / denominateur
    u = (q[0] * r[1] - q[1] * r[0]) / denominateur
    tolerance = 1e-7
    if -tolerance <= t <= 1 + tolerance and -tolerance <= u <= 1 + tolerance:
        return (a[0] + t * r[0], a[1] + t * r[1])
    return None


def contraindre_angle(origine: Point, p: Point, pas_degres: float = 45.0) -> Point:
    """Ramène p sur la direction multiple de « pas_degres » la plus proche (touche Maj)."""
    dx, dy = p[0] - origine[0], p[1] - origine[1]
    rayon = math.hypot(dx, dy)
    if rayon < EPSILON or pas_degres <= 0:
        return p
    angle = math.atan2(dy, dx)
    pas = math.radians(pas_degres)
    angle_cible = round(angle / pas) * pas
    # Projection sur la direction retenue : le point suit la souris le long de l'axe
    longueur = rayon * math.cos(angle - angle_cible)
    return (origine[0] + longueur * math.cos(angle_cible), origine[1] + longueur * math.sin(angle_cible))


def aplatir_bezier(p0: Point, p1: Point, p2: Point, p3: Point, pas: int = 8) -> list[Point]:
    """Discrétise une courbe de Bézier cubique en « pas » segments."""
    points = []
    for i in range(pas + 1):
        t = i / pas
        u = 1 - t
        x = u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0]
        y = u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]
        points.append((x, y))
    return points


def boite_englobante(points: Iterable[Point]) -> tuple[float, float, float, float]:
    """(xmin, ymin, xmax, ymax) d'un ensemble de points."""
    xs, ys = zip(*points)
    return min(xs), min(ys), max(xs), max(ys)


# ---------------------------------------------------------------------------
# Index spatial et accrochage
# ---------------------------------------------------------------------------

Segment = tuple[Point, Point, int]  # (a, b, drapeaux)


class IndexSegments:
    """Grille régulière associant chaque cellule aux segments qui la traversent.

    Un segment est échantillonné tous les demi-pas de cellule ; la requête
    élargit d'une cellule, ce qui garantit de ne rien manquer.
    """

    def __init__(self, segments: Sequence[Segment], taille_cellule: float) -> None:
        self.segments = list(segments)
        self.taille = max(float(taille_cellule), 1e-3)
        self._grille: dict[tuple[int, int], list[int]] = defaultdict(list)
        for indice, (a, b, _drapeaux) in enumerate(self.segments):
            for cellule in self._cellules_segment(a, b):
                self._grille[cellule].append(indice)

    def _cellule(self, p: Point) -> tuple[int, int]:
        return (math.floor(p[0] / self.taille), math.floor(p[1] / self.taille))

    def _cellules_segment(self, a: Point, b: Point) -> set[tuple[int, int]]:
        longueur = distance(a, b)
        nombre = max(1, int(math.ceil(longueur / (self.taille * 0.5))))
        cellules = set()
        for i in range(nombre + 1):
            t = i / nombre
            cellules.add(self._cellule((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))))
        return cellules

    def proches(self, p: Point, rayon: float) -> set[int]:
        """Indices des segments susceptibles de passer à moins de « rayon » de p."""
        cx0, cy0 = self._cellule((p[0] - rayon - self.taille, p[1] - rayon - self.taille))
        cx1, cy1 = self._cellule((p[0] + rayon + self.taille, p[1] + rayon + self.taille))
        # Garde-fou : rayon énorme (zoom très arrière) → on limite le balayage
        if (cx1 - cx0 + 1) * (cy1 - cy0 + 1) > 2500:
            return set()
        trouves: set[int] = set()
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                trouves.update(self._grille.get((cx, cy), ()))
        return trouves

    def __len__(self) -> int:
        return len(self.segments)


@dataclass(frozen=True)
class Accrochage:
    """Résultat d'une recherche d'accrochage."""

    point: Point
    type: str  # "extrémité", "intersection", "milieu", "sur trait", "libre"


@dataclass
class OptionsAccrochage:
    """Types d'accrochage activés (repris de la configuration)."""

    extremites: bool = True
    milieux: bool = True
    intersections: bool = True
    sur_trait: bool = True
    segments_max_intersections: int = 40


def accrocher(p: Point, index: IndexSegments | None, rayon: float,
              options: OptionsAccrochage, points_extra: Sequence[Point] = ()) -> Accrochage:
    """Cherche le point remarquable le plus proche de p dans le rayon donné.

    Priorité : points remarquables (extrémité, intersection, milieu, points des
    mesures existantes) au plus proche ; sinon projection sur le trait le plus
    proche ; sinon position libre.
    """
    candidats: list[tuple[float, Point, str]] = []

    # Sommets des mesures déjà tracées : permet d'enchaîner les mesures
    for q in points_extra:
        d = distance(p, q)
        if d <= rayon:
            candidats.append((d, q, "extrémité"))

    proches_trait: list[tuple[float, int, Point]] = []
    if index is not None and len(index):
        for i in index.proches(p, rayon):
            a, b, drapeaux = index.segments[i]
            projete, _t = projection_sur_segment(p, a, b)
            d_trait = distance(p, projete)
            if d_trait > rayon:
                continue
            proches_trait.append((d_trait, i, projete))
            if options.extremites:
                if drapeaux & EXTREMITE_A:
                    d = distance(p, a)
                    if d <= rayon:
                        candidats.append((d, a, "extrémité"))
                if drapeaux & EXTREMITE_B:
                    d = distance(p, b)
                    if d <= rayon:
                        candidats.append((d, b, "extrémité"))
            if options.milieux and drapeaux & SEGMENT_DROIT:
                m = milieu(a, b)
                d = distance(p, m)
                if d <= rayon:
                    candidats.append((d, m, "milieu"))

        if options.intersections and len(proches_trait) > 1:
            # Intersections limitées aux segments les plus proches (coût quadratique)
            voisins = sorted(proches_trait)[: options.segments_max_intersections]
            for k, (_d1, i, _p1) in enumerate(voisins):
                a, b, _ = index.segments[i]
                for _d2, j, _p2 in voisins[k + 1:]:
                    c, e, _ = index.segments[j]
                    x = intersection_segments(a, b, c, e)
                    if x is None:
                        continue
                    d = distance(p, x)
                    if d <= rayon:
                        candidats.append((d, x, "intersection"))

    if candidats:
        # Le plus proche l'emporte ; à égalité, l'ordre d'insertion favorise les extrémités
        d, q, nature = min(candidats, key=lambda c: c[0])
        return Accrochage(q, nature)
    if options.sur_trait and proches_trait:
        _d, _i, q = min(proches_trait, key=lambda c: c[0])
        return Accrochage(q, "sur trait")
    return Accrochage(p, "libre")

"""Motifs de remplissage techniques (dessin technique, architecture, VRD).

Chaque motif est généré dans un repère local (u, v) en points papier, centré
sur la forme, puis tourné (angle propre du motif + angle choisi), et enfin
DÉCOUPÉ EXACTEMENT par le contour de la forme. Le résultat est une liste de
primitives (segments, points pleins, petits cercles) consommée à l'identique
par l'écran et par l'export PDF : ce que l'on voit est ce qui est imprimé.

Les motifs « aléatoires » (béton, gravier…) utilisent un générateur pseudo-
aléatoire à graine fixe par cellule : le dessin est stable d'un affichage à l'autre.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable

from mesureplan import geometrie as geo

# Nombre maximal d'éléments générés : au-delà, l'espacement est augmenté automatiquement
ELEMENTS_MAX = 25_000


@dataclass
class Primitives:
    """Primitives d'un motif, en coordonnées de page (pt)."""

    segments: list[tuple[geo.Point, geo.Point]] = field(default_factory=list)
    points: list[tuple[geo.Point, float]] = field(default_factory=list)    # disques pleins (centre, rayon)
    cercles: list[tuple[geo.Point, float]] = field(default_factory=list)   # cercles évidés (centre, rayon)
    densite_reduite: bool = False  # vrai si l'espacement a été augmenté pour limiter le volume

    @property
    def taille(self) -> int:
        return len(self.segments) + len(self.points) + len(self.cercles)


# ---------------------------------------------------------------------------
# Générateurs : (demi-côté R du carré à couvrir, pas s) → primitives locales
# Convention locale : u vers la droite, v vers le bas (avant rotation).
# ---------------------------------------------------------------------------

Generateur = Callable[[float, float], Primitives]


def _graine(i: int, j: int) -> random.Random:
    return random.Random(i * 1_000_003 + j * 7_919 + 17)


def _lignes(R: float, s: float, decalage: float = 0.0) -> list[tuple[geo.Point, geo.Point]]:
    """Droites v = k·s + decalage couvrant le carré [-R, R]²."""
    n = int(math.ceil(R / s)) + 1
    return [((-R, k * s + decalage), (R, k * s + decalage)) for k in range(-n, n + 1)]


def _transposer(segments):
    return [((a[1], a[0]), (b[1], b[0])) for a, b in segments]


def _sinusoide(R: float, v0: float, amplitude: float, periode: float, phase: float = 0.0,
               pas: float | None = None) -> list[tuple[geo.Point, geo.Point]]:
    pas = pas or periode / 12
    n = int(2 * R / pas) + 2
    pts = [(-R + i * pas, v0 + amplitude * math.sin(2 * math.pi * (-R + i * pas) / periode + phase))
           for i in range(n)]
    return list(zip(pts, pts[1:]))


def _cellules(R: float, s: float):
    n = int(math.ceil(R / s)) + 1
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            yield i, j, i * s, j * s


def g_hachures(R, s):
    return Primitives(segments=_lignes(R, s))


def g_croisees(R, s):
    return Primitives(segments=_lignes(R, s) + _transposer(_lignes(R, s)))


def g_doubles(R, s):
    """Acier / métal : traits groupés par deux."""
    return Primitives(segments=_lignes(R, s) + _lignes(R, s, 0.3 * s))


def g_alternees(R, s):
    """Trait plein / trait interrompu alternés (maçonnerie, cloison)."""
    pleins = _lignes(R, 2 * s)
    tirets = []
    for (a, b) in _lignes(R, 2 * s, s):
        u = -R
        while u < R:
            tirets.append(((u, a[1]), (min(u + 0.6 * s, R), a[1])))
            u += s
    return Primitives(segments=pleins + tirets)


def g_beton(R, s):
    """Béton : petits triangles et granulats répartis irrégulièrement."""
    p = Primitives()
    for i, j, u, v in _cellules(R, s):
        g = _graine(i, j)
        cx, cy = u + g.random() * s, v + g.random() * s
        taille, rot = 0.28 * s * (0.7 + 0.6 * g.random()), g.random() * 2 * math.pi
        sommets = [(cx + taille * math.cos(rot + k * 2.1), cy + taille * math.sin(rot + k * 2.1)) for k in range(3)]
        p.segments += [(sommets[k], sommets[(k + 1) % 3]) for k in range(3)]
        for _ in range(2):
            p.points.append(((u + g.random() * s, v + g.random() * s), 0.035 * s))
    return p


def g_beton_arme(R, s):
    p = g_beton(R, s)
    p.segments += _lignes(R, 1.5 * s)
    return p


def g_enrobe(R, s):
    """Enrobé / route : semis dense de points fins."""
    p = Primitives()
    for i, j, u, v in _cellules(R, s):
        g = _graine(i, j)
        for _ in range(3):
            p.points.append(((u + g.random() * s, v + g.random() * s), 0.06 * s * (0.6 + g.random())))
    return p


def g_gravier(R, s):
    """Gravier / ballast : petits cercles irréguliers."""
    p = Primitives()
    for i, j, u, v in _cellules(R, s):
        g = _graine(i, j)
        p.cercles.append(((u + (0.25 + 0.5 * g.random()) * s, v + (0.25 + 0.5 * g.random()) * s),
                          s * (0.14 + 0.12 * g.random())))
        if g.random() < 0.5:
            p.points.append(((u + g.random() * s, v + g.random() * s), 0.04 * s))
    return p


def g_sable(R, s):
    p = Primitives()
    for i, j, u, v in _cellules(R, s):
        g = _graine(i, j)
        for _ in range(2):
            p.points.append(((u + g.random() * s, v + g.random() * s), 0.05 * s))
    return p


def g_terre(R, s):
    """Terre / remblai : rangées de traits courts alternant avec des points."""
    p = Primitives()
    for i, j, u, v in _cellules(R, s):
        if j % 2 == 0:
            decal = 0.5 * s if (j // 2) % 2 else 0.0
            p.segments.append(((u + decal, v), (u + decal + 0.55 * s, v)))
        else:
            p.points.append(((u + 0.25 * s, v), 0.05 * s))
            p.points.append(((u + 0.75 * s, v), 0.05 * s))
    return p


def g_terre_vegetale(R, s):
    """Terre végétale : touffes en quinconce sur un fond de points."""
    p = g_vegetal(R, s)
    for i, j, u, v in _cellules(R, s):
        g = _graine(i, j)
        p.points.append(((u + g.random() * s, v + g.random() * s), 0.04 * s))
    return p


def g_vegetal(R, s):
    """Végétalisation / gazon : touffes de trois brins en quinconce."""
    p = Primitives()
    for i, j, u, v in _cellules(R, s):
        base = (u + (0.5 * s if j % 2 else 0.0), v + 0.75 * s)
        h = 0.55 * s
        # Brins écartés en éventail (ne pas confondre avec une flèche) : centre, ±40° et ±70°
        for du, dv in ((0.0, -h), (-0.6 * h, -0.75 * h), (0.6 * h, -0.75 * h), (-0.85 * h, -0.3 * h), (0.85 * h, -0.3 * h)):
            p.segments.append((base, (base[0] + du, base[1] + dv)))
    return p


def g_terrasse(R, s):
    """Lames de terrasse / bardage : lames parallèles, aboutements décalés."""
    largeur, longueur = s, 7 * s
    p = Primitives(segments=_lignes(R, largeur))
    n = int(math.ceil(R / largeur)) + 1
    for k in range(-n, n):
        decalage = (k * 0.37 % 1.0) * longueur
        u = -R - longueur + decalage
        while u < R:
            p.segments.append(((u, k * largeur), (u, (k + 1) * largeur)))
            u += longueur
    return p


def g_parquet(R, s):
    """Parquet à bâtons rompus simplifié : lames courtes en quinconce."""
    p = Primitives(segments=_lignes(R, s))
    n = int(math.ceil(R / s)) + 1
    for k in range(-n, n):
        u = -R + (k % 2) * 2 * s
        while u < R:
            p.segments.append(((u, k * s), (u, (k + 1) * s)))
            u += 4 * s
    return p


def g_bois(R, s):
    """Bois (fil) : veinage ondulé."""
    p = Primitives()
    n = int(math.ceil(R / s)) + 1
    for k in range(-n, n + 1):
        p.segments += _sinusoide(R, k * s, 0.22 * s, 9 * s, phase=k * 0.9)
    return p


def g_bois_coupe(R, s):
    """Bois en coupe (bois de bout) : cernes concentriques."""
    p = Primitives()
    r = s
    while r < R * 1.5:
        n = max(16, int(2 * math.pi * r / (s * 0.5)))
        pts = [(r * math.cos(2 * math.pi * i / n) * 1.25, r * math.sin(2 * math.pi * i / n)) for i in range(n + 1)]
        p.segments += list(zip(pts, pts[1:]))
        r += s
    return p


def g_isolant(R, s):
    """Isolant souple (laine) : boucles sinusoïdales serrées entre deux traits."""
    hauteur = 4 * s
    p = Primitives()
    n = int(math.ceil(R / hauteur)) + 1
    for k in range(-n, n + 1):
        v0 = k * hauteur + hauteur / 2
        p.segments += _sinusoide(R, v0, 0.45 * hauteur, hauteur, pas=hauteur / 16)
    return p


def g_isolant_rigide(R, s):
    """Isolant rigide (polystyrène, PU) : losanges, traits croisés à ±30°."""
    p = Primitives()
    for angle in (30, -30):
        a = math.radians(angle)
        for (x0, y0), (x1, y1) in _lignes(R * 1.5, s * 2):
            p.segments.append(((x0 * math.cos(a) - y0 * math.sin(a), x0 * math.sin(a) + y0 * math.cos(a)),
                               (x1 * math.cos(a) - y1 * math.sin(a), x1 * math.sin(a) + y1 * math.cos(a))))
    return p


def _appareil(R, hauteur, longueur):
    p = Primitives(segments=_lignes(R, hauteur))
    n = int(math.ceil(R / hauteur)) + 1
    for k in range(-n, n):
        u = -R - longueur + (longueur / 2 if k % 2 else 0.0)
        while u < R:
            p.segments.append(((u, k * hauteur), (u, (k + 1) * hauteur)))
            u += longueur
    return p


def g_brique(R, s):
    return _appareil(R, s, 3.6 * s)


def g_parpaing(R, s):
    return _appareil(R, 2 * s, 4 * s)


def g_carrelage(R, s):
    return Primitives(segments=_lignes(R, s) + _transposer(_lignes(R, s)))


def g_eau(R, s):
    """Eau : petites vaguelettes en quinconce."""
    p = Primitives()
    for i, j, u, v in _cellules(R, s):
        u0 = u + (0.5 * s if j % 2 else 0.0)
        pts = [(u0 + 0.6 * s * t / 6, v + 0.08 * s * math.sin(math.pi * 2 * t / 6)) for t in range(7)]
        p.segments += list(zip(pts, pts[1:]))
    return p


def g_points(R, s):
    return Primitives(points=[((u, v), 0.07 * s) for _i, _j, u, v in _cellules(R, s)])


def g_pierre(R, s):
    """Enrochement / pierre : moellons polygonaux irréguliers."""
    p = Primitives()
    for i, j, u, v in _cellules(R, s):
        g = _graine(i, j)
        cx, cy = u + (0.5 if j % 2 else 0.0) * s + 0.5 * s, v + 0.5 * s
        n = 6
        pts = [(cx + 0.42 * s * (0.75 + 0.35 * g.random()) * math.cos(2 * math.pi * k / n + 0.3 * g.random()),
                cy + 0.42 * s * (0.75 + 0.35 * g.random()) * math.sin(2 * math.pi * k / n + 0.3 * g.random()))
               for k in range(n)]
        p.segments += [(pts[k], pts[(k + 1) % n]) for k in range(n)]
    return p


# code → (libellé, générateur, pas de base en pt, angle propre en degrés)
MOTIFS: dict[str, tuple[str, Generateur, float, float]] = {
    "hachures": ("Hachures simples (coupe générique)", g_hachures, 3.0, 45.0),
    "hachures_croisees": ("Hachures croisées", g_croisees, 3.0, 45.0),
    "acier": ("Acier / métal (hachures doubles)", g_doubles, 5.0, 45.0),
    "maconnerie": ("Maçonnerie (trait plein / interrompu)", g_alternees, 2.5, 45.0),
    "beton": ("Béton", g_beton, 7.0, 0.0),
    "beton_arme": ("Béton armé", g_beton_arme, 7.0, 45.0),
    "brique": ("Brique (appareil)", g_brique, 2.5, 0.0),
    "parpaing": ("Parpaing / bloc", g_parpaing, 3.0, 0.0),
    "pierre": ("Pierre / enrochement", g_pierre, 7.0, 0.0),
    "enrobe": ("Enrobé / route", g_enrobe, 2.5, 0.0),
    "gravier": ("Gravier / ballast", g_gravier, 4.5, 0.0),
    "sable": ("Sable", g_sable, 2.2, 0.0),
    "terre": ("Terre / remblai", g_terre, 3.5, 0.0),
    "terre_vegetale": ("Terre végétale", g_terre_vegetale, 6.0, 0.0),
    "vegetal": ("Végétalisation / gazon", g_vegetal, 6.0, 0.0),
    "terrasse": ("Lames de terrasse / bardage", g_terrasse, 4.0, 0.0),
    "parquet": ("Parquet", g_parquet, 3.0, 0.0),
    "bois": ("Bois (fil, veinage)", g_bois, 2.5, 0.0),
    "bois_coupe": ("Bois en coupe (bois de bout)", g_bois_coupe, 2.5, 0.0),
    "isolant": ("Isolant souple (laine)", g_isolant, 1.5, 0.0),
    "isolant_rigide": ("Isolant rigide (PSE, PU)", g_isolant_rigide, 3.0, 0.0),
    "carrelage": ("Carrelage", g_carrelage, 8.0, 0.0),
    "eau": ("Eau", g_eau, 6.0, 0.0),
    "points": ("Pointillé régulier", g_points, 3.0, 0.0),
}

# Nombre approximatif d'éléments par cellule s × s, pour estimer le volume avant génération
_ELEMENTS_PAR_CELLULE = {"beton": 5, "beton_arme": 6, "enrobe": 3, "gravier": 2, "sable": 2, "terre": 1,
                         "terre_vegetale": 6, "vegetal": 5, "eau": 6, "points": 1, "pierre": 6}


# ---------------------------------------------------------------------------
# Découpe par le contour
# ---------------------------------------------------------------------------

def _interieur(p: geo.Point, poly: list[geo.Point]) -> bool:
    x, y = p
    dedans = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            dedans = not dedans
    return dedans


def decouper_segment(a: geo.Point, b: geo.Point, poly: list[geo.Point],
                     boite: tuple[float, float, float, float]) -> list[tuple[geo.Point, geo.Point]]:
    """Parties du segment [a, b] situées à l'intérieur du polygone (règle pair-impair)."""
    bx0, by0, bx1, by1 = boite
    if max(a[0], b[0]) < bx0 or min(a[0], b[0]) > bx1 or max(a[1], b[1]) < by0 or min(a[1], b[1]) > by1:
        return []
    dx, dy = b[0] - a[0], b[1] - a[1]
    params = [0.0, 1.0]
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        ex, ey = q[0] - p[0], q[1] - p[1]
        den = dx * ey - dy * ex
        if abs(den) < 1e-12:
            continue
        t = ((p[0] - a[0]) * ey - (p[1] - a[1]) * ex) / den
        u = ((p[0] - a[0]) * dy - (p[1] - a[1]) * dx) / den
        # Tolérance sur u : un trait passant exactement par un sommet du contour doit être vu
        if 0.0 < t < 1.0 and -1e-9 <= u <= 1.0 + 1e-9:
            params.append(t)
    params.sort()
    morceaux = []
    for t0, t1 in zip(params, params[1:]):
        if t1 - t0 < 1e-9:
            continue
        tm = (t0 + t1) / 2
        if _interieur((a[0] + tm * dx, a[1] + tm * dy), poly):
            debut, fin = (a[0] + t0 * dx, a[1] + t0 * dy), (a[0] + t1 * dx, a[1] + t1 * dy)
            # Fusion avec le morceau précédent s'il est contigu
            if morceaux and geo.distance(morceaux[-1][1], debut) < 1e-9:
                morceaux[-1] = (morceaux[-1][0], fin)
            else:
                morceaux.append((debut, fin))
    return morceaux


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def generer(code: str, contour: list[geo.Point], angle: float = 0.0, echelle: float = 1.0) -> Primitives:
    """Génère le motif « code » découpé par le contour (polygone en pt de page)."""
    if code not in MOTIFS or len(contour) < 3:
        return Primitives()
    _libelle, generateur, pas_base, angle_propre = MOTIFS[code]
    boite = geo.boite_englobante(contour)
    centre = ((boite[0] + boite[2]) / 2, (boite[1] + boite[3]) / 2)
    R = max(math.hypot(boite[2] - boite[0], boite[3] - boite[1]) / 2, 1e-6)
    pas = max(pas_base * max(echelle, 0.05), 0.2)

    # Limitation du volume : estimation du nombre d'éléments avant génération
    densite_reduite = False
    elements = (2 * R / pas) ** 2 * _ELEMENTS_PAR_CELLULE.get(code, 0) + 4 * R / pas * 3
    if elements > ELEMENTS_MAX:
        pas *= math.sqrt(elements / ELEMENTS_MAX)
        densite_reduite = True

    local = generateur(R, pas)
    rotation = angle_propre + angle

    def placer(p: geo.Point) -> geo.Point:
        return geo.tourner((centre[0] + p[0], centre[1] + p[1]), centre, rotation)

    resultat = Primitives(densite_reduite=densite_reduite)
    for a, b in local.segments:
        resultat.segments += decouper_segment(placer(a), placer(b), contour, boite)
    for c, r in local.points:
        q = placer(c)
        if _interieur(q, contour):
            resultat.points.append((q, r))
    for c, r in local.cercles:
        q = placer(c)
        if _interieur(q, contour):
            resultat.cercles.append((q, r))
    return resultat


def libelles() -> list[tuple[str, str]]:
    """[(code, libellé)] dans l'ordre d'affichage, précédé de l'option « aucun »."""
    return [("", "Aucun motif")] + [(code, valeurs[0]) for code, valeurs in MOTIFS.items()]

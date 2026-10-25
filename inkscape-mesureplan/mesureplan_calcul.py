"""Calculs purs de l'extension Inkscape « Mesure de plan » (aucune dépendance à inkex).

Les géométries arrivent sous forme de « superchemin » cubique (format inkex
CubicSuperPath : liste de sous-chemins, chaque nœud = [poignée entrante,
nœud, poignée sortante]), déjà exprimé en unités utilisateur de la racine SVG.
"""

from __future__ import annotations

import json
import math
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field

Point = tuple[float, float]

# Facteurs vers le millimètre des unités CSS/SVG
MM_PAR_UNITE = {"mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 25.4 / 72, "pc": 25.4 / 6,
                "px": 25.4 / 96, "": 25.4 / 96, "m": 1000.0, "q": 0.25}
FACTEURS_AFFICHAGE = {"m": 1.0, "cm": 100.0, "mm": 1000.0}
PAS_COURBE = 16  # segments par courbe de Bézier non rectiligne


# ---------------------------------------------------------------------------
# Unités du document
# ---------------------------------------------------------------------------

def longueur_css_en_mm(texte: str) -> float:
    """« 420mm », « 1190.55pt », « 1587 » (px) → millimètres."""
    m = re.fullmatch(r"\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([a-zA-Z]*)\s*", texte or "")
    if not m:
        raise ValueError(f"Longueur SVG illisible : {texte!r}")
    unite = m.group(2).lower()
    if unite not in MM_PAR_UNITE:
        raise ValueError(f"Unité non gérée : {unite} (les pourcentages ne sont pas supportés)")
    return float(m.group(1)) * MM_PAR_UNITE[unite]


def mm_papier_par_uu(largeur: str | None, viewbox: str | None) -> float:
    """Millimètres « papier » représentés par une unité utilisateur de la racine SVG.

    Sans viewBox, l'unité utilisateur vaut 1 px CSS (1/96 de pouce).
    """
    if not viewbox:
        return MM_PAR_UNITE["px"]
    valeurs = [float(v) for v in re.split(r"[\s,]+", viewbox.strip()) if v]
    if len(valeurs) != 4 or valeurs[2] <= 0:
        raise ValueError(f"viewBox invalide : {viewbox!r}")
    if not largeur:
        return MM_PAR_UNITE["px"]  # largeur absente : 1 uu = 1 px par convention
    return longueur_css_en_mm(largeur) / valeurs[2]


# ---------------------------------------------------------------------------
# Géométrie des superchemins
# ---------------------------------------------------------------------------

def _bezier(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
    u = 1 - t
    return (u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
            u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1])


def _est_rectiligne(p0: Point, p1: Point, p2: Point, p3: Point, tolerance: float = 1e-9) -> bool:
    """Vrai si les poignées sont alignées sur la corde (segment droit)."""
    dx, dy = p3[0] - p0[0], p3[1] - p0[1]
    corde = math.hypot(dx, dy)
    if corde < tolerance:
        return math.dist(p0, p1) < tolerance and math.dist(p0, p2) < tolerance
    for p in (p1, p2):
        if abs((p[0] - p0[0]) * dy - (p[1] - p0[1]) * dx) / corde > 1e-6 * max(corde, 1.0):
            return False
    return True


@dataclass
class SousChemin:
    """Sous-chemin aplati : nœuds réels + polyligne discrétisée."""

    noeuds: list[Point]
    polyligne: list[Point]
    ferme: bool
    rectiligne: bool  # True si tous les segments sont droits


def aplatir(superchemin: list, fermes: list[bool]) -> list[SousChemin]:
    """Discrétise chaque sous-chemin ; « fermes » indique les sous-chemins clos (commande Z)."""
    resultat = []
    for indice, sous in enumerate(superchemin):
        if not sous:
            continue
        noeuds = [tuple(n[1]) for n in sous]
        polyligne = [noeuds[0]]
        rectiligne = True
        for i in range(len(sous) - 1):
            p0, p1, p2, p3 = tuple(sous[i][1]), tuple(sous[i][2]), tuple(sous[i + 1][0]), tuple(sous[i + 1][1])
            if _est_rectiligne(p0, p1, p2, p3):
                polyligne.append(p3)
            else:
                rectiligne = False
                polyligne.extend(_bezier(p0, p1, p2, p3, k / PAS_COURBE) for k in range(1, PAS_COURBE + 1))
        ferme = fermes[indice] if indice < len(fermes) else False
        # Un sous-chemin dont le dernier nœud rejoint le premier est fermé de fait
        if len(noeuds) > 2 and math.dist(noeuds[0], noeuds[-1]) < 1e-6:
            ferme = True
        # Supprime le doublon final éventuel (Z qui ramène au départ)
        if ferme and len(noeuds) > 1 and math.dist(noeuds[0], noeuds[-1]) < 1e-6:
            noeuds.pop()
        if ferme and len(polyligne) > 1 and math.dist(polyligne[0], polyligne[-1]) < 1e-6:
            polyligne.pop()
        resultat.append(SousChemin(noeuds, polyligne, ferme, rectiligne))
    return resultat


def longueur(points: list[Point], ferme: bool) -> float:
    total = sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1))
    if ferme and len(points) > 2:
        total += math.dist(points[-1], points[0])
    return total


def aire(points: list[Point]) -> float:
    """Aire par la formule du lacet (valeur absolue)."""
    if len(points) < 3:
        return 0.0
    s = 0.0
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def centroide(points: list[Point]) -> Point:
    a = 0.0
    cx = cy = 0.0
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        f = x1 * y2 - x2 * y1
        a += f
        cx += (x1 + x2) * f
        cy += (y1 + y2) * f
    if abs(a) < 1e-12:
        n = len(points)
        return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n)
    return (cx / (3 * a), cy / (3 * a))


def angle_sommet(a: Point, s: Point, b: Point) -> float:
    """Angle en degrés (0–180) entre les bras s→a et s→b."""
    v1, v2 = (a[0] - s[0], a[1] - s[1]), (b[0] - s[0], b[1] - s[1])
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if n1 < 1e-12 or n2 < 1e-12:
        return 0.0
    c = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def angle_entre_droites(a1: Point, a2: Point, b1: Point, b2: Point) -> float:
    """Angle aigu (0–90°) entre deux droites ; l'obtus vaut 180 − résultat."""
    u = (a2[0] - a1[0], a2[1] - a1[1])
    v = (b2[0] - b1[0], b2[1] - b1[1])
    nu, nv = math.hypot(*u), math.hypot(*v)
    if nu < 1e-12 or nv < 1e-12:
        return 0.0
    c = abs(u[0] * v[0] + u[1] * v[1]) / (nu * nv)
    return math.degrees(math.acos(min(1.0, c)))


def point_bissectrice(a: Point, s: Point, b: Point, distance: float) -> Point:
    """Point situé à « distance » du sommet s, sur la bissectrice de l'angle a-s-b."""
    u = (a[0] - s[0], a[1] - s[1])
    v = (b[0] - s[0], b[1] - s[1])
    nu, nv = math.hypot(*u) or 1.0, math.hypot(*v) or 1.0
    d = (u[0] / nu + v[0] / nv, u[1] / nu + v[1] / nv)
    nd = math.hypot(*d)
    if nd < 1e-12:  # angle plat : on décale perpendiculairement
        d, nd = (-u[1] / nu, u[0] / nu), 1.0
    return (s[0] + d[0] / nd * distance, s[1] + d[1] / nd * distance)


def intersection_droites(a1: Point, a2: Point, b1: Point, b2: Point) -> Point:
    """Intersection des droites (a1a2) et (b1b2) ; milieu des milieux si parallèles."""
    r = (a2[0] - a1[0], a2[1] - a1[1])
    s = (b2[0] - b1[0], b2[1] - b1[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-12:
        return ((a1[0] + a2[0] + b1[0] + b2[0]) / 4, (a1[1] + a2[1] + b1[1] + b2[1]) / 4)
    t = ((b1[0] - a1[0]) * s[1] - (b1[1] - a1[1]) * s[0]) / den
    return (a1[0] + t * r[0], a1[1] + t * r[1])


# ---------------------------------------------------------------------------
# Échelle du document
# ---------------------------------------------------------------------------

@dataclass
class EchelleDocument:
    """Échelle stockée dans le SVG (JSON dans un élément <metadata>)."""

    mm_par_uu: float
    denominateur: float = 100.0
    origine: str = "défaut"
    references: list[dict] = field(default_factory=list)  # {"longueur_uu":…, "longueur_m":…}

    @property
    def facteur_cartouche(self) -> float:
        """Mètres réels par unité utilisateur selon le cartouche."""
        return self.mm_par_uu / 1000.0 * self.denominateur

    @property
    def facteur(self) -> float:
        if self.references:
            return statistics.fmean(r["longueur_m"] / r["longueur_uu"] for r in self.references)
        return self.facteur_cartouche

    @property
    def denominateur_effectif(self) -> float:
        return self.facteur * 1000.0 / self.mm_par_uu

    @property
    def ecart_pct(self) -> float | None:
        return (self.facteur / self.facteur_cartouche - 1) * 100 if self.references else None

    @property
    def dispersion_pct(self) -> float | None:
        if len(self.references) < 2:
            return None
        f = [r["longueur_m"] / r["longueur_uu"] for r in self.references]
        return (max(f) - min(f)) / statistics.fmean(f) * 100

    def ajouter_reference(self, longueur_uu: float, longueur_m: float, remplacer: bool) -> None:
        if longueur_uu <= 0 or longueur_m <= 0:
            raise ValueError("Longueurs de référence strictement positives requises")
        if remplacer:
            self.references.clear()
        self.references.append({"longueur_uu": longueur_uu, "longueur_m": longueur_m})

    def vers_json(self) -> str:
        return json.dumps({"denominateur": self.denominateur, "origine": self.origine,
                           "references": self.references}, ensure_ascii=False)

    @classmethod
    def depuis_json(cls, texte: str | None, mm_par_uu: float, denominateur_defaut: float) -> "EchelleDocument":
        if not texte:
            return cls(mm_par_uu, denominateur_defaut)
        d = json.loads(texte)
        return cls(mm_par_uu, float(d.get("denominateur", denominateur_defaut)), d.get("origine", "saisie"),
                   list(d.get("references", [])))

    def synthese(self, fmt: "Formateur") -> str:
        lignes = [f"Échelle appliquée : {texte_echelle(self.denominateur_effectif)} "
                  f"({'calibrée sur %d cote(s)' % len(self.references) if self.references else 'cartouche ' + self.origine})",
                  f"Échelle du cartouche : {texte_echelle(self.denominateur)}"]
        if self.ecart_pct is not None:
            lignes.append(f"Écart calibration / cartouche : {fmt.nombre(self.ecart_pct, 2)} %")
        if self.dispersion_pct is not None:
            lignes.append(f"Cohérence des cotes de référence : {fmt.nombre(self.dispersion_pct, 2)} % d'écart max")
        elif not self.references:
            lignes.append("⚠ Échelle non vérifiée : calibrez sur une cote connue.")
        return "\n".join(lignes)


def texte_echelle(d: float) -> str:
    return f"1:{int(round(d))}" if abs(d - round(d)) < 1e-6 else f"1:{d:.2f}".replace(".", ",")


# ---------------------------------------------------------------------------
# Détection de l'échelle dans le texte du plan
# ---------------------------------------------------------------------------

ECHELLES_USUELLES = {5, 10, 20, 25, 50, 75, 100, 125, 150, 200, 250, 500, 1000, 2000, 2500, 5000}
MOTIF = re.compile(r"(?<![\d/.,])1\s*[/:]\s*(\d{1,4}(?:[.,]\d+)?)(?![\d/])")
MOTS_CLES = ("ech", "éch", "scale")


def detecter_echelle(texte: str) -> float | None:
    """Dénominateur le plus probable (mot-clé « Éch. » prioritaire), ou None."""
    scores: Counter[float] = Counter()
    for m in MOTIF.finditer(texte):
        d = float(m.group(1).replace(",", "."))
        mot_cle = any(k in texte[max(0, m.start() - 20): m.start()].lower() for k in MOTS_CLES)
        if mot_cle or d in ECHELLES_USUELLES:
            scores[d] += 3 if mot_cle else 1
    return scores.most_common(1)[0][0] if scores else None


# ---------------------------------------------------------------------------
# Mise en forme
# ---------------------------------------------------------------------------

@dataclass
class Formateur:
    unite: str = "m"
    decimales: int = 2
    decimales_surface: int = 2
    decimales_angle: int = 1

    @staticmethod
    def nombre(v: float, d: int) -> str:
        return f"{v:,.{d}f}".replace(",", " ").replace(".", ",")

    def longueur(self, metres: float) -> str:
        return f"{self.nombre(metres * FACTEURS_AFFICHAGE[self.unite], self.decimales)} {self.unite}"

    def surface(self, m2: float) -> str:
        return f"{self.nombre(m2, self.decimales_surface)} m²"

    def angle(self, degres: float) -> str:
        return f"{self.nombre(degres, self.decimales_angle)}°"

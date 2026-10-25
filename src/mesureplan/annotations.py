"""Annotations graphiques du plan (modèle pur, sans dépendance graphique).

Comme les mesures, les annotations sont stockées en points PDF dans le repère
de la page : épaisseurs et tailles de police sont des grandeurs « papier »
(en pt), identiques à l'écran et dans le PDF exporté.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import Enum

from mesureplan import geometrie as geo


class TypeAnnotation(str, Enum):
    LIGNE = "ligne"
    FLECHE = "flèche"
    POLYLIGNE = "polyligne"
    POLYGONE = "polygone"
    RECTANGLE = "rectangle"
    ELLIPSE = "ellipse"
    CERCLE = "cercle"
    TEXTE = "texte"


# Formes tracées par glisser (deux points : départ / arrivée)
TYPES_GLISSER = {TypeAnnotation.LIGNE, TypeAnnotation.FLECHE, TypeAnnotation.RECTANGLE,
                 TypeAnnotation.ELLIPSE, TypeAnnotation.CERCLE}
# Formes pouvant recevoir un fond
TYPES_REMPLISSABLES = {TypeAnnotation.POLYGONE, TypeAnnotation.RECTANGLE, TypeAnnotation.ELLIPSE,
                       TypeAnnotation.CERCLE, TypeAnnotation.TEXTE}

# Formes dont l'orientation se règle (souris ou saisie d'angle)
TYPES_ORIENTABLES = {TypeAnnotation.RECTANGLE, TypeAnnotation.ELLIPSE, TypeAnnotation.LIGNE, TypeAnnotation.FLECHE}
# Formes pouvant recevoir un motif de remplissage (hachures, matériaux…)
TYPES_MOTIF = {TypeAnnotation.RECTANGLE, TypeAnnotation.ELLIPSE, TypeAnnotation.CERCLE, TypeAnnotation.POLYGONE}

STYLES_TRAIT = ("plein", "tirets", "pointillés")
SEGMENTS_ELLIPSE = 72  # discrétisation des ellipses tournées (rendu et export identiques)

# Proportions typographiques communes à l'écran et à l'export
INTERLIGNE = 1.25        # hauteur de ligne / taille de police
LIGNE_DE_BASE = 0.9      # position de la ligne de base de la 1re ligne / taille
MARGE_TEXTE = 0.3        # marge intérieure du cadre / taille
CHASSE_MOYENNE = 0.55    # largeur moyenne d'un caractère / taille (estimation hors rendu)


@dataclass
class Style:
    """Apparence d'une annotation. couleur_fond = None : fond transparent."""

    couleur_trait: str = "#D81B60"
    couleur_fond: str | None = None
    opacite_fond: float = 0.35
    epaisseur: float = 1.5           # pt papier
    trait: str = "plein"             # plein, tirets, pointillés
    taille_police: float = 10.0      # pt papier
    cadre_texte: bool = True
    double_fleche: bool = False
    # Motif de remplissage technique ("" : aucun) — voir mesureplan.motifs
    motif: str = ""
    motif_angle: float = 0.0          # degrés, ajoutés à l'orientation propre du motif
    motif_echelle: float = 1.0        # multiplicateur de l'espacement du motif
    motif_couleur: str | None = None  # None : couleur du trait
    motif_epaisseur: float = 0.3      # pt papier

    def copie(self) -> "Style":
        return Style(**asdict(self))

    def vers_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def depuis_dict(cls, d: dict) -> "Style":
        connus = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**connus)


@dataclass
class Annotation:
    """Annotation d'une page.

    Points selon le type :
      ligne, flèche : [départ, arrivée] (la pointe est à l'arrivée) ;
      rectangle, ellipse : deux coins opposés ;
      cercle : [centre, point du cercle] ;
      polyligne, polygone : sommets ;
      texte : [ancre] (coin haut-gauche, ou centre si « centre » est vrai).

    Rectangle et ellipse portent en plus un angle (degrés, sens trigonométrique
    à l'écran) : les deux coins décrivent la forme AVANT rotation autour de son centre.
    Lignes et flèches sont tournées en déplaçant directement leurs extrémités.
    """

    identifiant: int
    type: TypeAnnotation
    page: int
    points: list[geo.Point]
    style: Style = field(default_factory=Style)
    texte: str = ""
    centre: bool = False
    angle: float = 0.0

    # --- Géométrie -----------------------------------------------------------
    def copie(self) -> "Annotation":
        return Annotation(self.identifiant, self.type, self.page, list(self.points), self.style.copie(),
                          self.texte, self.centre, self.angle)

    @property
    def tournee(self) -> bool:
        return self.type in (TypeAnnotation.RECTANGLE, TypeAnnotation.ELLIPSE) and abs(self.angle % 360) > 1e-9

    def centre_geometrique(self) -> geo.Point:
        """Centre de rotation / de référence de l'annotation."""
        if self.type is TypeAnnotation.CERCLE:
            return self.points[0]
        if self.type is TypeAnnotation.POLYGONE:
            return geo.centroide_polygone(self.points)
        x0, y0, x1, y1 = self.boite()
        return ((x0 + x1) / 2, (y0 + y1) / 2)

    def coins(self) -> list[geo.Point]:
        """Rectangle / ellipse : les 4 coins de la boîte, rotation appliquée (ordre : HG, HD, BD, BG)."""
        x0, y0, x1, y1 = self.boite()
        c = ((x0 + x1) / 2, (y0 + y1) / 2)
        return [geo.tourner(q, c, self.angle) for q in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]

    def contour(self) -> list[geo.Point]:
        """Polygone du contour des formes fermées (rotation appliquée), pour remplissage et motifs."""
        if self.type is TypeAnnotation.POLYGONE:
            return list(self.points)
        if self.type is TypeAnnotation.RECTANGLE:
            return self.coins()
        if self.type in (TypeAnnotation.ELLIPSE, TypeAnnotation.CERCLE):
            x0, y0, x1, y1 = self.boite()
            c = ((x0 + x1) / 2, (y0 + y1) / 2)
            rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
            angle = self.angle if self.type is TypeAnnotation.ELLIPSE else 0.0
            return [geo.tourner((c[0] + rx * math.cos(2 * math.pi * i / SEGMENTS_ELLIPSE),
                                 c[1] + ry * math.sin(2 * math.pi * i / SEGMENTS_ELLIPSE)), c, angle)
                    for i in range(SEGMENTS_ELLIPSE)]
        if self.type is TypeAnnotation.TEXTE:
            x0, y0, x1, y1 = self.boite()
            return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        return list(self.points)

    def boite_englobante(self) -> tuple[float, float, float, float]:
        """Emprise réelle à l'écran (rotation comprise)."""
        if self.type in (TypeAnnotation.RECTANGLE, TypeAnnotation.ELLIPSE) and self.tournee:
            return geo.boite_englobante(self.contour())
        return self.boite()

    # --- Orientation -----------------------------------------------------------
    @property
    def orientation(self) -> float | None:
        """Angle affiché et saisissable (°), ou None si le type n'est pas orientable."""
        if self.type in (TypeAnnotation.RECTANGLE, TypeAnnotation.ELLIPSE):
            return _normaliser_angle(self.angle)
        if self.type in (TypeAnnotation.LIGNE, TypeAnnotation.FLECHE):
            return _normaliser_angle(geo.orientation_degres(self.points[0], self.points[1]))
        return None

    def tourner_de(self, delta: float) -> None:
        """Rotation de « delta » degrés autour du centre."""
        if self.type in (TypeAnnotation.RECTANGLE, TypeAnnotation.ELLIPSE):
            self.angle = _normaliser_angle(self.angle + delta)
        elif self.type is not TypeAnnotation.TEXTE:
            c = self.centre_geometrique()
            self.points = [geo.tourner(p, c, delta) for p in self.points]

    def definir_orientation(self, angle: float) -> None:
        actuel = self.orientation
        if actuel is not None:
            self.tourner_de(angle - actuel)

    # --- Poignées d'édition -------------------------------------------------------
    def poignees(self) -> list[geo.Point]:
        """Points déplaçables à la souris (indices utilisés par deplacer_poignee)."""
        if self.type in (TypeAnnotation.RECTANGLE, TypeAnnotation.ELLIPSE):
            return self.coins()
        if self.type is TypeAnnotation.TEXTE:
            return []
        return list(self.points)

    def deplacer_poignee(self, indice: int, q: geo.Point) -> None:
        """Déplace une poignée ; pour un rectangle / ovale, le coin opposé reste fixe et l'angle est conservé."""
        if self.type in (TypeAnnotation.RECTANGLE, TypeAnnotation.ELLIPSE):
            fixe = self.coins()[(indice + 2) % 4]
            c = geo.milieu(fixe, q)
            # Coordonnées « avant rotation » des deux coins autour du nouveau centre
            self.points = [geo.tourner(fixe, c, -self.angle), geo.tourner(q, c, -self.angle)]
        elif self.type is TypeAnnotation.CERCLE and indice == 0:
            self.deplacer(q[0] - self.points[0][0], q[1] - self.points[0][1])
        elif 0 <= indice < len(self.points):
            self.points[indice] = q
    @property
    def rayon(self) -> float:
        return geo.distance(self.points[0], self.points[1]) if self.type is TypeAnnotation.CERCLE else 0.0

    def boite(self, largeur_texte: float | None = None) -> tuple[float, float, float, float]:
        """Boîte englobante (x0, y0, x1, y1). Pour un texte, largeur mesurée si fournie, sinon estimée."""
        if self.type is TypeAnnotation.CERCLE:
            (cx, cy), r = self.points[0], self.rayon
            return (cx - r, cy - r, cx + r, cy + r)
        if self.type is TypeAnnotation.TEXTE:
            largeur, hauteur = taille_bloc_texte(self.texte, self.style.taille_police, largeur_texte)
            x, y = self.points[0]
            if self.centre:
                x, y = x - largeur / 2, y - hauteur / 2
            return (x, y, x + largeur, y + hauteur)
        return geo.boite_englobante(self.points)

    def distance(self, p: geo.Point) -> float:
        """Distance de p à l'annotation ; 0 à l'intérieur d'une forme pleine ou d'un texte."""
        if self.tournee:
            # Ramené dans le repère de la forme non tournée
            p = geo.tourner(p, self.centre_geometrique(), -self.angle)
        x0, y0, x1, y1 = self.boite()
        if self.type is TypeAnnotation.TEXTE:
            return _distance_rectangle(p, x0, y0, x1, y1)
        rempli = (self.style.couleur_fond is not None or bool(self.style.motif)) and self.type in TYPES_REMPLISSABLES
        if self.type in (TypeAnnotation.LIGNE, TypeAnnotation.FLECHE, TypeAnnotation.POLYLIGNE,
                         TypeAnnotation.POLYGONE):
            sommets = list(self.points)
            if self.type is TypeAnnotation.POLYGONE:
                if rempli and point_dans_polygone(p, sommets):
                    return 0.0
                sommets.append(sommets[0])
            return min(geo.distance(p, geo.projection_sur_segment(p, a, b)[0])
                       for a, b in zip(sommets, sommets[1:]))
        if self.type is TypeAnnotation.RECTANGLE:
            if rempli and x0 <= p[0] <= x1 and y0 <= p[1] <= y1:
                return 0.0
            coins = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
            return min(geo.distance(p, geo.projection_sur_segment(p, a, b)[0]) for a, b in zip(coins, coins[1:]))
        # Ellipse et cercle : distance approchée par normalisation radiale
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        rx, ry = max((x1 - x0) / 2, 1e-9), max((y1 - y0) / 2, 1e-9)
        dx, dy = p[0] - cx, p[1] - cy
        rho = math.hypot(dx / rx, dy / ry)
        if rempli and rho <= 1:
            return 0.0
        return abs(rho - 1) * min(rx, ry)

    def deplacer(self, dx: float, dy: float) -> None:
        self.points = [(x + dx, y + dy) for x, y in self.points]

    # --- Persistance -----------------------------------------------------------
    def vers_dict(self) -> dict:
        return {"identifiant": self.identifiant, "type": self.type.value, "page": self.page,
                "points": [list(p) for p in self.points], "style": self.style.vers_dict(),
                "texte": self.texte, "centre": self.centre, "angle": self.angle}

    @classmethod
    def depuis_dict(cls, d: dict) -> "Annotation":
        return cls(int(d["identifiant"]), TypeAnnotation(d["type"]), int(d["page"]),
                   [tuple(p) for p in d["points"]], Style.depuis_dict(d.get("style", {})),
                   str(d.get("texte", "")), bool(d.get("centre", False)), float(d.get("angle", 0.0)))


# ---------------------------------------------------------------------------
# Outils géométriques et de rendu partagés (écran / PDF)
# ---------------------------------------------------------------------------

def _normaliser_angle(a: float) -> float:
    """Angle ramené dans ]-180 ; 180]."""
    a = math.fmod(a, 360.0)
    if a <= -180.0:
        a += 360.0
    elif a > 180.0:
        a -= 360.0
    return a


def _distance_rectangle(p: geo.Point, x0: float, y0: float, x1: float, y1: float) -> float:
    dx = max(x0 - p[0], 0.0, p[0] - x1)
    dy = max(y0 - p[1], 0.0, p[1] - y1)
    return math.hypot(dx, dy)


def point_dans_polygone(p: geo.Point, polygone: list[geo.Point]) -> bool:
    """Test pair-impair."""
    x, y = p
    dedans = False
    for i in range(len(polygone)):
        x1, y1 = polygone[i]
        x2, y2 = polygone[(i + 1) % len(polygone)]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            dedans = not dedans
    return dedans


def taille_bloc_texte(texte: str, taille: float, largeur_mesuree: float | None = None) -> tuple[float, float]:
    """Largeur et hauteur du cadre d'un texte (marges comprises)."""
    lignes = texte.split("\n") or [""]
    marge = MARGE_TEXTE * taille
    if largeur_mesuree is None:
        largeur_mesuree = max(len(ligne) for ligne in lignes) * CHASSE_MOYENNE * taille
    return largeur_mesuree + 2 * marge, len(lignes) * INTERLIGNE * taille + 2 * marge


def longueur_pointe(epaisseur: float) -> float:
    """Longueur de la pointe de flèche (pt), proportionnée à l'épaisseur du trait."""
    return max(6.0, 4.5 * epaisseur)


def pointe_fleche(queue: geo.Point, tete: geo.Point, longueur: float,
                  demi_angle: float = 22.0) -> list[geo.Point]:
    """Triangle de la pointe : [tête, aile gauche, aile droite]."""
    angle = math.atan2(tete[1] - queue[1], tete[0] - queue[0])
    a = math.radians(demi_angle)
    return [tete,
            (tete[0] - longueur * math.cos(angle - a), tete[1] - longueur * math.sin(angle - a)),
            (tete[0] - longueur * math.cos(angle + a), tete[1] - longueur * math.sin(angle + a))]


def recul_pointe(queue: geo.Point, tete: geo.Point, longueur: float) -> geo.Point:
    """Point où arrêter le trait pour que son extrémité carrée ne dépasse pas de la pointe."""
    d = geo.distance(queue, tete)
    if d < 1e-9:
        return tete
    k = max(d - longueur * 0.8, 0.0) / d
    return (queue[0] + (tete[0] - queue[0]) * k, queue[1] + (tete[1] - queue[1]) * k)


def motif_tirets(trait: str, epaisseur: float) -> list[float] | None:
    """Motif de tirets en pt (None : trait plein)."""
    e = max(epaisseur, 0.3)
    if trait == "tirets":
        return [4 * e, 2.5 * e]
    if trait == "pointillés":
        return [0.01, 2.2 * e]  # quasi-points rendus ronds par l'extrémité arrondie
    return None


def hex_vers_rgb(couleur: str) -> tuple[float, float, float]:
    """« #E4572E » → (0,894, 0,341, 0,180)."""
    c = couleur.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return tuple(int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


# Caractères hors Latin-1 (non couverts par la police Helvetica standard du PDF)
SUBSTITUTIONS_PDF = {"Σ": "Tot.", " ": " ", " ": " ", "⚠": "!", "–": "-", "—": "-",
                     "’": "'", "“": '"', "”": '"', "…": "...", "œ": "oe", "Œ": "OE", "€": "EUR"}


def texte_pdf(texte: str) -> str:
    """Rend un texte compatible avec la police Helvetica standard (Latin-1)."""
    for source, cible in SUBSTITUTIONS_PDF.items():
        texte = texte.replace(source, cible)
    return texte.encode("latin-1", errors="replace").decode("latin-1")


# ---------------------------------------------------------------------------
# Conversion des mesures en primitives (pour l'export PDF)
# ---------------------------------------------------------------------------

def primitives_mesure(mesure, echelle, formateur, couleur: str) -> list[Annotation]:
    """Transforme une mesure en annotations dessinables (trait + étiquette centrée)."""
    from mesureplan.mesures import TypeMesure  # import local : évite un cycle d'import

    style_trait = Style(couleur_trait=couleur, epaisseur=0.8)
    style_etiquette = Style(couleur_trait=couleur, couleur_fond="#FFFFFF", opacite_fond=0.85,
                            epaisseur=0.5, taille_police=7.0, cadre_texte=True)
    pts = list(mesure.points)
    formes: list[Annotation] = []
    if mesure.type is TypeMesure.SURFACE:
        style_surface = style_trait.copie()
        style_surface.couleur_fond, style_surface.opacite_fond = couleur, 0.15
        formes.append(Annotation(0, TypeAnnotation.POLYGONE, mesure.page, pts, style_surface))
        position = geo.centroide_polygone(pts)
    elif mesure.type is TypeMesure.ANGLE:
        formes.append(Annotation(0, TypeAnnotation.POLYLIGNE, mesure.page, pts, style_trait))
        a, s, b = pts[:3]
        # Étiquette sur la bissectrice, à 30 % du bras le plus court
        r = 0.3 * min(geo.distance(s, a), geo.distance(s, b))
        u = (a[0] - s[0], a[1] - s[1])
        v = (b[0] - s[0], b[1] - s[1])
        nu, nv = math.hypot(*u) or 1.0, math.hypot(*v) or 1.0
        d = (u[0] / nu + v[0] / nv, u[1] / nu + v[1] / nv)
        nd = math.hypot(*d) or 1.0
        position = (s[0] + d[0] / nd * r * 1.6, s[1] + d[1] / nd * r * 1.6)
    elif mesure.type is TypeMesure.CHAINE:
        formes.append(Annotation(0, TypeAnnotation.POLYLIGNE, mesure.page, pts, style_trait))
        k = (len(pts) - 1) // 2
        position = geo.milieu(pts[k], pts[k + 1])
    else:
        formes.append(Annotation(0, TypeAnnotation.LIGNE, mesure.page, pts[:2], style_trait))
        position = geo.milieu(pts[0], pts[-1])
    formes.append(Annotation(0, TypeAnnotation.TEXTE, mesure.page, [position], style_etiquette,
                             formateur.etiquette(mesure, echelle), centre=True))
    return formes

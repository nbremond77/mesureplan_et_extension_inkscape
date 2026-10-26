"""Éléments graphiques Qt : mesures, annotations (rotation, motifs), poignées, repères.

Toute la géométrie vient du modèle pur (annotations.py, motifs.py) : l'écran
et l'export PDF dessinent exactement les mêmes contours et les mêmes motifs.
"""

from __future__ import annotations

import math
from collections import OrderedDict

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QPolygonF, QTransform
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem

from mesureplan import annotations as ann
from mesureplan import geometrie as geo
from mesureplan import motifs
from mesureplan.annotations import Annotation, Style, TypeAnnotation

# Plans de dessin (z) : motifs < annotations < mesures < étiquettes < poignées
Z_MOTIF, Z_ANNOTATION, Z_TEXTE, Z_MESURE, Z_SOMMET = 21, 22, 25, 30, 40
Z_ETIQUETTE, Z_SELECTION, Z_POIGNEE, Z_MARQUEUR = 60, 70, 75, 80


# ---------------------------------------------------------------------------
# Éléments à taille constante à l'écran
# ---------------------------------------------------------------------------

class Etiquette(QGraphicsItem):
    """Cartouche de texte lisible quel que soit le zoom (ignore les transformations)."""

    def __init__(self, texte: str, couleur: QColor, taille_police: float = 9.0,
                 decalage: tuple[float, float] = (0.0, 0.0), parent: QGraphicsItem | None = None) -> None:
        super().__init__(parent)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setZValue(Z_ETIQUETTE)
        self._couleur = QColor(couleur)
        self._police = QFont()
        self._police.setPointSizeF(taille_police)
        self._police.setBold(True)
        self._decalage = decalage
        self._texte = None
        self._rect = QRectF()
        self.definir_texte(texte)

    def definir_texte(self, texte: str) -> None:
        if texte == self._texte:
            return
        self.prepareGeometryChange()
        self._texte = texte
        fm = QFontMetricsF(self._police)
        lignes = texte.split("\n") or [""]
        largeur = max(fm.horizontalAdvance(ligne) for ligne in lignes)
        hauteur = fm.height() * len(lignes)
        dx, dy = self._decalage
        # Centré sur la position, sauf décalage demandé (aperçu près du curseur)
        x0 = dx if dx else -largeur / 2 - 6
        y0 = dy if dy else -hauteur / 2 - 3
        self._rect = QRectF(x0, y0, largeur + 12, hauteur + 6)
        self.update()

    def boundingRect(self) -> QRectF:  # noqa: N802 — API Qt
        return self._rect.adjusted(-1, -1, 1, 1)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: ARG002
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(self._couleur, 1.4))
        painter.setBrush(QColor(255, 255, 255, 232))
        painter.drawRoundedRect(self._rect, 4, 4)
        painter.setFont(self._police)
        painter.setPen(self._couleur.darker(140))
        painter.drawText(self._rect, Qt.AlignmentFlag.AlignCenter, self._texte or "")


class MarqueurAccrochage(QGraphicsItem):
    """Symbole d'accrochage (convention CAO) : carré = extrémité, triangle = milieu,
    croix = intersection, sablier = sur trait, petite croix = libre."""

    TAILLE = 7.0
    COULEURS = {"extrémité": "#00A651", "milieu": "#00A0E0", "intersection": "#F39200",
                "sur trait": "#9B59B6", "libre": "#7F7F7F"}

    def __init__(self) -> None:
        super().__init__()
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setZValue(Z_MARQUEUR)
        self.type_accrochage = "libre"

    def definir_type(self, type_accrochage: str) -> None:
        if type_accrochage != self.type_accrochage:
            self.type_accrochage = type_accrochage
            self.update()

    def boundingRect(self) -> QRectF:  # noqa: N802
        t = self.TAILLE + 3
        return QRectF(-t, -t, 2 * t, 2 * t)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: ARG002
        t = self.TAILLE
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(self.COULEURS.get(self.type_accrochage, "#7F7F7F")), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.type_accrochage == "extrémité":
            painter.drawRect(QRectF(-t, -t, 2 * t, 2 * t))
        elif self.type_accrochage == "milieu":
            painter.drawPolygon(QPolygonF([QPointF(0, -t), QPointF(t, t * 0.8), QPointF(-t, t * 0.8)]))
        elif self.type_accrochage == "intersection":
            painter.drawLine(QPointF(-t, -t), QPointF(t, t))
            painter.drawLine(QPointF(-t, t), QPointF(t, -t))
        elif self.type_accrochage == "sur trait":
            painter.drawPolygon(QPolygonF([QPointF(-t, -t), QPointF(t, -t), QPointF(-t, t), QPointF(t, t)]))
        else:
            painter.drawLine(QPointF(-4, 0), QPointF(4, 0))
            painter.drawLine(QPointF(0, -4), QPointF(0, 4))


class Sommet(QGraphicsItem):
    """Petit disque marquant un sommet de mesure (taille écran constante)."""

    def __init__(self, couleur: QColor, rayon: float = 3.0) -> None:
        super().__init__()
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setZValue(Z_SOMMET)
        self._couleur = QColor(couleur)
        self._rayon = rayon

    def boundingRect(self) -> QRectF:  # noqa: N802
        r = self._rayon + 1
        return QRectF(-r, -r, 2 * r, 2 * r)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: ARG002
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor("white"), 1))
        painter.setBrush(self._couleur)
        painter.drawEllipse(QRectF(-self._rayon, -self._rayon, 2 * self._rayon, 2 * self._rayon))


class Poignee(QGraphicsItem):
    """Poignée d'édition : carré (sommet / coin) ou rond (rotation), taille écran constante."""

    DEMI_COTE = 5.0

    def __init__(self, couleur: QColor, rotation: bool = False) -> None:
        super().__init__()
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setZValue(Z_POIGNEE)
        self._couleur = QColor(couleur)
        self._rotation = rotation

    def boundingRect(self) -> QRectF:  # noqa: N802
        d = self.DEMI_COTE + 2
        return QRectF(-d, -d, 2 * d, 2 * d)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: ARG002
        d = self.DEMI_COTE
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(self._couleur, 1.6))
        painter.setBrush(QColor("white"))
        if self._rotation:
            painter.drawEllipse(QRectF(-d, -d, 2 * d, 2 * d))
            painter.drawArc(QRectF(-d / 2, -d / 2, d, d), 30 * 16, 270 * 16)
        else:
            painter.drawRect(QRectF(-d, -d, 2 * d, 2 * d))


def stylo_cosmetique(couleur: QColor | str, largeur: float = 2.0, pointille: bool = False) -> QPen:
    """Stylo d'épaisseur constante à l'écran."""
    stylo = QPen(QColor(couleur), largeur)
    stylo.setCosmetic(True)
    stylo.setCapStyle(Qt.PenCapStyle.RoundCap)
    stylo.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    if pointille:
        stylo.setStyle(Qt.PenStyle.DashLine)
    return stylo


# ---------------------------------------------------------------------------
# Annotations
# ---------------------------------------------------------------------------

class TexteAnnotation(QGraphicsItem):
    """Texte d'annotation à l'échelle du plan (taille en pt papier, comme dans le PDF exporté)."""

    TAILLE_REFERENCE = 100  # police rendue à 100 px puis réduite : précision sub-point

    def __init__(self, a: Annotation) -> None:
        super().__init__()
        st = a.style
        self.setZValue(Z_TEXTE)
        self._lignes = a.texte.split("\n")
        self._taille = st.taille_police
        self._police = QFont("Helvetica")
        self._police.setPixelSize(self.TAILLE_REFERENCE)
        fm = QFontMetricsF(self._police)
        largeur = max(fm.horizontalAdvance(ligne) for ligne in self._lignes) * self._taille / self.TAILLE_REFERENCE
        x0, y0, x1, y1 = a.boite(largeur)
        self.rect = QRectF(x0, y0, x1 - x0, y1 - y0)
        self._couleur = QColor(st.couleur_trait)
        self._fond: QColor | None = None
        if st.couleur_fond:
            self._fond = QColor(st.couleur_fond)
            self._fond.setAlphaF(max(0.0, min(1.0, st.opacite_fond)))
        self._cadre = st.cadre_texte
        self._epaisseur_cadre = max(0.4, st.epaisseur * 0.5)

    def boundingRect(self) -> QRectF:  # noqa: N802
        e = self._epaisseur_cadre
        return self.rect.adjusted(-e, -e, e, e)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: ARG002
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        if self._fond is not None or self._cadre:
            painter.setPen(QPen(self._couleur, self._epaisseur_cadre) if self._cadre else QPen(Qt.PenStyle.NoPen))
            painter.setBrush(QBrush(self._fond) if self._fond is not None else QBrush(Qt.BrushStyle.NoBrush))
            painter.drawRect(self.rect)
        painter.setPen(self._couleur)
        painter.setFont(self._police)
        marge = ann.MARGE_TEXTE * self._taille
        reduction = self._taille / self.TAILLE_REFERENCE
        for i, ligne in enumerate(self._lignes):
            base = self.rect.top() + marge + self._taille * (ann.LIGNE_DE_BASE + i * ann.INTERLIGNE)
            painter.save()
            painter.translate(self.rect.left() + marge, base)
            painter.scale(reduction, reduction)
            painter.drawText(QPointF(0, 0), ligne)
            painter.restore()


def stylo_annotation(style: Style) -> QPen:
    """Stylo à l'échelle du plan (épaisseur en pt papier), tirets selon le style."""
    stylo = QPen(QColor(style.couleur_trait), max(style.epaisseur, 0.05))
    stylo.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    motif = ann.motif_tirets(style.trait, style.epaisseur)
    if motif:
        # Qt exprime les tirets en multiples de l'épaisseur
        e = max(style.epaisseur, 0.3)
        stylo.setDashPattern([max(v / e, 0.01) for v in motif])
        stylo.setCapStyle(Qt.PenCapStyle.RoundCap if style.trait == "pointillés" else Qt.PenCapStyle.FlatCap)
    else:
        stylo.setCapStyle(Qt.PenCapStyle.FlatCap)
    return stylo


# Cache des motifs : leur génération (découpe exacte) est coûteuse, la géométrie change rarement
_CACHE_MOTIFS: OrderedDict = OrderedDict()
TAILLE_CACHE_MOTIFS = 300


def primitives_motif(a: Annotation) -> motifs.Primitives | None:
    """Motif de remplissage de l'annotation (mis en cache), ou None."""
    st = a.style
    if not st.motif or a.type not in ann.TYPES_MOTIF:
        return None
    contour = a.contour()
    cle = (st.motif, round(st.motif_angle, 4), round(st.motif_echelle, 4),
           tuple((round(x, 3), round(y, 3)) for x, y in contour))
    if cle in _CACHE_MOTIFS:
        _CACHE_MOTIFS.move_to_end(cle)
        return _CACHE_MOTIFS[cle]
    resultat = motifs.generer(st.motif, contour, st.motif_angle, st.motif_echelle)
    _CACHE_MOTIFS[cle] = resultat
    while len(_CACHE_MOTIFS) > TAILLE_CACHE_MOTIFS:
        _CACHE_MOTIFS.popitem(last=False)
    return resultat


def _items_motif(a: Annotation) -> list[QGraphicsItem]:
    prim = primitives_motif(a)
    if prim is None or not prim.taille:
        return []
    st = a.style
    couleur = QColor(st.motif_couleur or st.couleur_trait)
    items: list[QGraphicsItem] = []
    if prim.segments or prim.cercles:
        chemin = QPainterPath()
        for p, q in prim.segments:
            chemin.moveTo(QPointF(*p))
            chemin.lineTo(QPointF(*q))
        for c, r in prim.cercles:
            chemin.addEllipse(QPointF(*c), r, r)
        trace = QGraphicsPathItem(chemin)
        stylo = QPen(couleur, max(st.motif_epaisseur, 0.05))
        stylo.setCapStyle(Qt.PenCapStyle.RoundCap)
        trace.setPen(stylo)
        trace.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        items.append(trace)
    if prim.points:
        chemin = QPainterPath()
        for c, r in prim.points:
            chemin.addEllipse(QPointF(*c), r, r)
        points = QGraphicsPathItem(chemin)
        points.setPen(QPen(Qt.PenStyle.NoPen))
        points.setBrush(QBrush(couleur))
        items.append(points)
    for item in items:
        item.setZValue(Z_MOTIF)
    return items


def items_annotation(a: Annotation) -> list[QGraphicsItem]:
    """Éléments graphiques d'une annotation (même géométrie qu'à l'export PDF)."""
    st = a.style
    if a.type is TypeAnnotation.TEXTE:
        return [TexteAnnotation(a)]
    pinceau = QBrush(Qt.BrushStyle.NoBrush)
    if st.couleur_fond and a.type in ann.TYPES_REMPLISSABLES:
        couleur_fond = QColor(st.couleur_fond)
        couleur_fond.setAlphaF(max(0.0, min(1.0, st.opacite_fond)))
        pinceau = QBrush(couleur_fond)
    chemin = QPainterPath()
    items: list[QGraphicsItem] = []
    if a.type is TypeAnnotation.FLECHE:
        queue, tete = a.points[0], a.points[1]
        longueur = ann.longueur_pointe(st.epaisseur)
        debut = ann.recul_pointe(tete, queue, longueur) if st.double_fleche else queue
        chemin.moveTo(QPointF(*debut))
        chemin.lineTo(QPointF(*ann.recul_pointe(queue, tete, longueur)))
        pointes = QPainterPath()
        triangles = [ann.pointe_fleche(queue, tete, longueur)]
        if st.double_fleche:
            triangles.append(ann.pointe_fleche(tete, queue, longueur))
        for triangle in triangles:
            pointes.addPolygon(QPolygonF([QPointF(*p) for p in triangle]))
            pointes.closeSubpath()
        item_pointes = QGraphicsPathItem(pointes)
        stylo_pointes = QPen(QColor(st.couleur_trait), 0.5)
        stylo_pointes.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        item_pointes.setPen(stylo_pointes)
        item_pointes.setBrush(QBrush(QColor(st.couleur_trait)))
        items.append(item_pointes)
    elif a.type in (TypeAnnotation.LIGNE, TypeAnnotation.POLYLIGNE, TypeAnnotation.POLYGONE):
        chemin.moveTo(QPointF(*a.points[0]))
        for p in a.points[1:]:
            chemin.lineTo(QPointF(*p))
        if a.type is TypeAnnotation.POLYGONE:
            chemin.closeSubpath()
    elif a.type is TypeAnnotation.RECTANGLE:
        chemin.addPolygon(QPolygonF([QPointF(*p) for p in a.coins()]))
        chemin.closeSubpath()
    else:  # ellipse, cercle : vraie courbe, tournée autour du centre si besoin
        x0, y0, x1, y1 = a.boite()
        chemin.addEllipse(QRectF(x0, y0, x1 - x0, y1 - y0))
        if a.tournee:
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            # Qt tourne dans le sens horaire à l'écran : angle opposé
            chemin = QTransform().translate(cx, cy).rotate(-a.angle).translate(-cx, -cy).map(chemin)
    trace = QGraphicsPathItem(chemin)
    trace.setPen(stylo_annotation(st))
    trace.setBrush(pinceau)
    items.insert(0, trace)
    for item in items:
        item.setZValue(Z_ANNOTATION)
    # Le motif se dessine au-dessus du fond mais sous le contour
    return _items_motif(a) + items


def cadre_selection(a: Annotation, rect_texte: QRectF | None, couleur: QColor) -> QGraphicsItem:
    """Contour de sélection pointillé (suit la rotation des rectangles et ovales)."""
    if rect_texte is not None:
        contour = [(rect_texte.left(), rect_texte.top()), (rect_texte.right(), rect_texte.top()),
                   (rect_texte.right(), rect_texte.bottom()), (rect_texte.left(), rect_texte.bottom())]
    elif a.type in (TypeAnnotation.RECTANGLE, TypeAnnotation.ELLIPSE):
        contour = a.coins()
    else:
        x0, y0, x1, y1 = a.boite()
        contour = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    chemin = QPainterPath()
    chemin.addPolygon(QPolygonF([QPointF(*p) for p in contour]))
    chemin.closeSubpath()
    item = QGraphicsPathItem(chemin)
    item.setPen(stylo_cosmetique(couleur, 1.3, pointille=True))
    item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    item.setZValue(Z_SELECTION)
    return item


# ---------------------------------------------------------------------------
# Mesures
# ---------------------------------------------------------------------------

def jambes_decomposition(a: geo.Point, b: geo.Point, couleur: QColor) -> QGraphicsItem:
    """Côtés ΔX (horizontal) et ΔY (vertical) en tirets, avec un petit repère d'angle droit."""
    coin = ann.coin_decomposition(a, b)
    chemin = QPainterPath(QPointF(*a))
    chemin.lineTo(QPointF(*coin))
    chemin.lineTo(QPointF(*b))
    # Repère d'angle droit : carré de côté proportionnel au plus petit des deux côtés
    cote = 0.12 * min(abs(b[0] - a[0]), abs(b[1] - a[1]))
    if cote > 0:
        sx = -1.0 if b[0] > a[0] else 1.0   # vers a, le long de l'horizontale
        sy = 1.0 if b[1] > a[1] else -1.0   # vers b, le long de la verticale
        chemin.moveTo(QPointF(coin[0] + sx * cote, coin[1]))
        chemin.lineTo(QPointF(coin[0] + sx * cote, coin[1] + sy * cote))
        chemin.lineTo(QPointF(coin[0], coin[1] + sy * cote))
    item = QGraphicsPathItem(chemin)
    item.setPen(stylo_cosmetique(couleur, 1.2, pointille=True))
    item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    item.setZValue(Z_MESURE - 1)
    return item


def items_mesure(type_mesure: str, points: list[geo.Point], texte: str, couleur: QColor, largeur: float,
                 taille_police: float, pointille: bool = False) -> list[QGraphicsItem]:
    """Trait, sommets et étiquette d'une mesure (ou d'une cote de référence)."""
    chemin = QPainterPath(QPointF(*points[0]))
    for p in points[1:]:
        chemin.lineTo(QPointF(*p))
    trace = QGraphicsPathItem()
    trace.setZValue(Z_MESURE)
    trace.setPen(stylo_cosmetique(couleur, largeur, pointille))
    if type_mesure == "surface":
        chemin.closeSubpath()
        remplissage = QColor(couleur)
        remplissage.setAlpha(45)
        trace.setBrush(QBrush(remplissage))
        position = geo.centroide_polygone(points)
    elif type_mesure == "angle" and len(points) == 3:
        a, s, b = points
        rayon = min(geo.distance(s, a), geo.distance(s, b)) * 0.3
        a1, a2 = geo.orientation_degres(s, a), geo.orientation_degres(s, b)
        balayage = (a2 - a1 + 540.0) % 360.0 - 180.0
        boite = QRectF(s[0] - rayon, s[1] - rayon, 2 * rayon, 2 * rayon)
        chemin.arcMoveTo(boite, a1)
        chemin.arcTo(boite, a1, balayage)
        milieu_angle = math.radians(a1 + balayage / 2.0)
        position = (s[0] + 1.6 * rayon * math.cos(milieu_angle), s[1] - 1.6 * rayon * math.sin(milieu_angle))
    elif type_mesure == "chaîne" and len(points) > 2:
        k = (len(points) - 1) // 2
        position = geo.milieu(points[k], points[k + 1])
    else:
        position = geo.milieu(points[0], points[-1])
    trace.setPath(chemin)
    items: list[QGraphicsItem] = [trace]
    if type_mesure == "distance XY" and len(points) >= 2:
        items.append(jambes_decomposition(points[0], points[-1], couleur))
    for p in points:
        sommet = Sommet(couleur)
        sommet.setPos(QPointF(*p))
        items.append(sommet)
    etiquette = Etiquette(texte, couleur, taille_police)
    etiquette.setPos(QPointF(*position))
    items.append(etiquette)
    return items

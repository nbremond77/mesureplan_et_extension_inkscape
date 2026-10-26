"""Icônes des outils dessinées par programme (aucun fichier image à embarquer)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

COULEUR_TRAIT = QColor("#2B2F36")
COULEUR_ACCENT = QColor("#E4572E")
COULEUR_REFERENCE = QColor("#2E9E4F")
COULEUR_ANNOTATION = QColor("#1F77D0")


def _stylo(couleur: QColor, largeur: float = 2.2) -> QPen:
    stylo = QPen(couleur, largeur)
    stylo.setCapStyle(Qt.PenCapStyle.RoundCap)
    stylo.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return stylo


def icone(nom: str, taille: int = 32) -> QIcon:
    """Retourne l'icône de l'outil « nom » (navigation, distance, chaine, surface, angle, calibrer, ajuster)."""
    pix = QPixmap(taille, taille)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.scale(taille / 32.0, taille / 32.0)  # dessin sur une grille 32×32

    if nom == "navigation":
        # Quatre flèches de déplacement
        p.setPen(_stylo(COULEUR_TRAIT))
        p.drawLine(QPointF(16, 4), QPointF(16, 28))
        p.drawLine(QPointF(4, 16), QPointF(28, 16))
        for (x, y), (dx, dy) in (((16, 4), (0, 1)), ((16, 28), (0, -1)), ((4, 16), (1, 0)), ((28, 16), (-1, 0))):
            p.drawLine(QPointF(x, y), QPointF(x + 4 * dx + 4 * dy, y + 4 * dy + 4 * dx))
            p.drawLine(QPointF(x, y), QPointF(x + 4 * dx - 4 * dy, y + 4 * dy - 4 * dx))
    elif nom == "distance":
        p.setPen(_stylo(COULEUR_ACCENT, 2.6))
        p.drawLine(QPointF(5, 22), QPointF(27, 10))
        p.setPen(_stylo(COULEUR_TRAIT, 2.0))
        p.drawLine(QPointF(3, 18), QPointF(7, 26))
        p.drawLine(QPointF(25, 6), QPointF(29, 14))
    elif nom == "distance_xy":
        # Hypoténuse pleine + côtés ΔX / ΔY en tirets
        stylo_tirets = _stylo(COULEUR_TRAIT, 1.8)
        stylo_tirets.setStyle(Qt.PenStyle.DashLine)
        p.setPen(stylo_tirets)
        p.drawLine(QPointF(5, 26), QPointF(27, 26))
        p.drawLine(QPointF(27, 26), QPointF(27, 6))
        p.setPen(_stylo(COULEUR_ACCENT, 2.6))
        p.drawLine(QPointF(5, 26), QPointF(27, 6))
        p.setPen(_stylo(COULEUR_TRAIT, 1.4))
        p.drawPolyline(QPolygonF([QPointF(23, 26), QPointF(23, 22), QPointF(27, 22)]))
    elif nom == "chaine":
        p.setPen(_stylo(COULEUR_ACCENT, 2.6))
        p.drawPolyline(QPolygonF([QPointF(4, 26), QPointF(10, 10), QPointF(20, 20), QPointF(28, 6)]))
        p.setBrush(COULEUR_TRAIT)
        p.setPen(Qt.PenStyle.NoPen)
        for x, y in ((4, 26), (10, 10), (20, 20), (28, 6)):
            p.drawEllipse(QPointF(x, y), 2.4, 2.4)
    elif nom == "surface":
        polygone = QPolygonF([QPointF(4, 8), QPointF(22, 4), QPointF(28, 22), QPointF(14, 28), QPointF(6, 20)])
        couleur = QColor(COULEUR_ACCENT)
        couleur.setAlpha(80)
        p.setBrush(couleur)
        p.setPen(_stylo(COULEUR_ACCENT, 2.4))
        p.drawPolygon(polygone)
    elif nom == "angle":
        p.setPen(_stylo(COULEUR_TRAIT, 2.4))
        p.drawLine(QPointF(5, 27), QPointF(29, 27))
        p.drawLine(QPointF(5, 27), QPointF(22, 5))
        chemin = QPainterPath()
        boite = QRectF(-7, 15, 24, 24)
        chemin.arcMoveTo(boite, 0)
        chemin.arcTo(boite, 0, 52)
        p.setPen(_stylo(COULEUR_ACCENT, 2.4))
        p.drawPath(chemin)
    elif nom == "calibrer":
        # Règle graduée + coche
        p.setPen(_stylo(COULEUR_REFERENCE, 2.0))
        p.setBrush(QColor(46, 158, 79, 50))
        p.drawRect(QRectF(3, 10, 26, 10))
        for i, x in enumerate(range(6, 28, 4)):
            p.drawLine(QPointF(x, 10), QPointF(x, 14 if i % 2 else 16))
        p.setPen(_stylo(COULEUR_ACCENT, 2.6))
        p.drawPolyline(QPolygonF([QPointF(16, 26), QPointF(20, 30), QPointF(29, 22)]))
    elif nom == "ajuster":
        p.setPen(_stylo(COULEUR_TRAIT, 2.2))
        for x, y, dx, dy in ((4, 4, 1, 1), (28, 4, -1, 1), (4, 28, 1, -1), (28, 28, -1, -1)):
            p.drawLine(QPointF(x, y), QPointF(x + 7 * dx, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + 7 * dy))
        p.drawRect(QRectF(11, 11, 10, 10))
    elif nom == "aimant":
        p.setPen(_stylo(COULEUR_ACCENT, 5))
        chemin = QPainterPath(QPointF(8, 6))
        chemin.lineTo(QPointF(8, 17))
        chemin.arcTo(QRectF(8, 9, 16, 16), 180, 180)
        chemin.lineTo(QPointF(24, 6))
        p.drawPath(chemin)
        p.setPen(_stylo(COULEUR_TRAIT, 5))
        p.drawLine(QPointF(8, 4), QPointF(8, 8))
        p.drawLine(QPointF(24, 4), QPointF(24, 8))
    # --- Outils d'annotation (couleur distincte des outils de mesure)
    elif nom == "fleche":
        p.setPen(_stylo(COULEUR_ANNOTATION, 2.6))
        p.drawLine(QPointF(5, 27), QPointF(23, 9))
        p.setBrush(COULEUR_ANNOTATION)
        p.drawPolygon(QPolygonF([QPointF(28, 4), QPointF(17, 8), QPointF(24, 15)]))
    elif nom == "ligne":
        p.setPen(_stylo(COULEUR_ANNOTATION, 2.6))
        p.drawLine(QPointF(5, 27), QPointF(27, 5))
    elif nom == "polyligne":
        p.setPen(_stylo(COULEUR_ANNOTATION, 2.4))
        p.drawPolyline(QPolygonF([QPointF(4, 24), QPointF(12, 8), QPointF(20, 22), QPointF(28, 8)]))
    elif nom == "polygone":
        couleur = QColor(COULEUR_ANNOTATION)
        couleur.setAlpha(70)
        p.setBrush(couleur)
        p.setPen(_stylo(COULEUR_ANNOTATION, 2.2))
        p.drawPolygon(QPolygonF([QPointF(16, 4), QPointF(28, 13), QPointF(23, 28), QPointF(9, 28), QPointF(4, 13)]))
    elif nom == "rectangle":
        p.setPen(_stylo(COULEUR_ANNOTATION, 2.4))
        p.drawRect(QRectF(5, 8, 22, 16))
    elif nom == "ellipse":
        p.setPen(_stylo(COULEUR_ANNOTATION, 2.4))
        p.drawEllipse(QRectF(3, 9, 26, 14))
    elif nom == "cercle":
        p.setPen(_stylo(COULEUR_ANNOTATION, 2.4))
        p.drawEllipse(QRectF(5, 5, 22, 22))
        p.setBrush(COULEUR_ANNOTATION)
        p.drawEllipse(QPointF(16, 16), 1.6, 1.6)
    elif nom == "texte":
        police = QFont("Serif")
        police.setPixelSize(26)
        police.setBold(True)
        p.setFont(police)
        p.setPen(COULEUR_ANNOTATION)
        p.drawText(QRectF(0, 0, 32, 32), Qt.AlignmentFlag.AlignCenter, "T")
    elif nom == "pdf":
        p.setPen(_stylo(COULEUR_TRAIT, 1.8))
        p.setBrush(QColor("white"))
        p.drawPolygon(QPolygonF([QPointF(7, 3), QPointF(20, 3), QPointF(26, 9), QPointF(26, 29), QPointF(7, 29)]))
        p.setPen(_stylo(COULEUR_ANNOTATION, 2.6))
        p.drawLine(QPointF(10, 24), QPointF(20, 14))
        p.setBrush(COULEUR_ANNOTATION)
        p.drawPolygon(QPolygonF([QPointF(23, 11), QPointF(16, 13), QPointF(21, 18)]))
    elif nom == "imprimante":
        p.setPen(_stylo(COULEUR_TRAIT, 1.8))
        p.setBrush(QColor("white"))
        p.drawRect(QRectF(9, 3, 14, 9))                       # feuille entrante
        p.setBrush(QColor("#C9CED6"))
        p.drawRoundedRect(QRectF(3, 11, 26, 11), 2, 2)        # corps
        p.setBrush(QColor("white"))
        p.drawRect(QRectF(9, 18, 14, 11))                     # feuille sortante
        p.setPen(_stylo(COULEUR_ACCENT, 1.6))
        p.drawLine(QPointF(11, 23), QPointF(21, 23))          # trait coté
        p.drawLine(QPointF(11, 21), QPointF(11, 25))
        p.drawLine(QPointF(21, 21), QPointF(21, 25))
    p.end()
    return QIcon(pix)

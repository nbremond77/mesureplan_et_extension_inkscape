"""Vue interactive du plan : rendu, zoom/panoramique, accrochage, tracé et édition.

Repère de scène = repère de la page PDF en points : une mesure tracée ici
est directement exploitable par le noyau de calcul.

Édition (outil Naviguer) :
  - clic : sélection ; glisser un élément : déplacement (Maj : horizontal / vertical) ;
  - glisser une poignée carrée : déplacement du sommet, avec accrochage
    (Ctrl : sans accrochage, Maj : direction contrainte) ; Ctrl+clic : suppression du sommet ;
  - glisser la poignée ronde : rotation (Maj : pas de 15°) ;
  - double-clic sur un côté de chaîne / surface / polyligne / polygone : ajout d'un sommet ;
  - clic droit : désélection. Dans un outil de tracé, le clic droit termine le tracé
    en cours s'il est valide, puis revient à l'outil Naviguer.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsLineItem, QGraphicsPathItem, QGraphicsPixmapItem,
                               QGraphicsRectItem, QGraphicsScene, QGraphicsView)

from mesureplan import annotations as ann
from mesureplan import geometrie as geo
from mesureplan.annotations import Annotation, Style, TypeAnnotation
from mesureplan.pdf_document import DocumentPDF
from mesureplan.rendu_elements import (Etiquette, MarqueurAccrochage, Poignee, cadre_selection, items_annotation,
                                       items_mesure, stylo_cosmetique)

journal = logging.getLogger(__name__)

ZOOM_MIN, ZOOM_MAX = 0.03, 400.0          # pixels écran par point PDF
DECALAGE_ETIQUETTE_APERCU = (22.0, 22.0)  # pixels : l'aperçu ne masque pas le curseur
RAYON_POIGNEE_PX = 9.0                    # tolérance de saisie d'une poignée
DISTANCE_POIGNEE_ROTATION_PX = 28.0       # éloignement de la poignée de rotation
PAS_ROTATION_CONTRAINTE = 15.0            # degrés, avec Maj


class Outil(Enum):
    NAVIGATION = "Naviguer"
    DISTANCE = "Distance"
    DISTANCE_XY = "Distance XY"
    CHAINE = "Chaîne"
    SURFACE = "Surface"
    ANGLE = "Angle"
    CALIBRATION = "Calibrer"
    # Annotations
    FLECHE = "Flèche"
    LIGNE = "Ligne"
    POLYLIGNE = "Polyligne"
    POLYGONE = "Polygone"
    RECTANGLE = "Rectangle"
    ELLIPSE = "Ellipse"
    CERCLE = "Cercle"
    TEXTE = "Texte"


# Outil d'annotation → type d'annotation créé
ANNOTATION_PAR_OUTIL = {
    Outil.FLECHE: TypeAnnotation.FLECHE, Outil.LIGNE: TypeAnnotation.LIGNE,
    Outil.POLYLIGNE: TypeAnnotation.POLYLIGNE, Outil.POLYGONE: TypeAnnotation.POLYGONE,
    Outil.RECTANGLE: TypeAnnotation.RECTANGLE, Outil.ELLIPSE: TypeAnnotation.ELLIPSE,
    Outil.CERCLE: TypeAnnotation.CERCLE, Outil.TEXTE: TypeAnnotation.TEXTE,
}
# Outils d'annotation tracés par glisser (appui → relâchement)
OUTILS_GLISSER = {o for o, t in ANNOTATION_PAR_OUTIL.items() if t in ann.TYPES_GLISSER}

# Outils terminés automatiquement après un nombre fixe de points
POINTS_FIXES = {Outil.DISTANCE: 2, Outil.DISTANCE_XY: 2, Outil.ANGLE: 3, Outil.CALIBRATION: 2}
# Outils à nombre de points libre : minimum requis pour terminer
POINTS_MINIMUM = {Outil.CHAINE: 2, Outil.SURFACE: 3, Outil.POLYLIGNE: 2, Outil.POLYGONE: 3}

# Types (mesures et annotations) dont on peut ajouter / supprimer des sommets ; valeur = minimum
SOMMETS_MODIFIABLES = {"chaîne": 2, "surface": 3, TypeAnnotation.POLYLIGNE.value: 2,
                       TypeAnnotation.POLYGONE.value: 3}
TYPES_FERMES = {"surface", TypeAnnotation.POLYGONE.value}


@dataclass
class ElementAffiche:
    """Élément (mesure ou annotation) tel que connu de la vue."""

    identifiant: int
    type: str                          # valeur du type de mesure ou d'annotation
    points: list[geo.Point]
    texte: str = ""                    # étiquette (mesures)
    annotation: Annotation | None = None

    @property
    def est_annotation(self) -> bool:
        return self.annotation is not None


@dataclass
class Edition:
    """Glisser en cours sur un élément existant."""

    element: ElementAffiche
    nature: str                        # "deplacer", "sommet", "rotation"
    indice: int
    depart: geo.Point
    points0: list[geo.Point]
    annotation0: Annotation | None
    centre: geo.Point = (0.0, 0.0)
    angle_souris0: float = 0.0
    points: list[geo.Point] = field(default_factory=list)
    angle: float = 0.0
    modifie: bool = False


class VuePlan(QGraphicsView):
    """Vue interactive du plan."""

    mesure_terminee = Signal(object, object)       # (Outil, liste de points)
    reference_tracee = Signal(object)              # liste de 2 points
    position_changee = Signal(float, float, str)   # x, y (pt), type d'accrochage
    outil_change = Signal(object)                  # Outil
    mesure_cliquee = Signal(int)                   # identifiant sélectionné (-1 : aucun) — mesure ou annotation
    annotation_tracee = Signal(object, object)     # (TypeAnnotation, liste de points)
    texte_demande = Signal(object)                 # point d'ancrage d'un nouveau texte
    geometrie_modifiee = Signal(int, object, object)  # identifiant, nouveaux points, angle (annotations) ou None
    element_double_clic = Signal(int)              # identifiant de l'élément double-cliqué

    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self._cfg = config
        cfg_acc = config["accrochage"]
        self.options_accrochage = geo.OptionsAccrochage(
            extremites=cfg_acc.get("extremites", True), milieux=cfg_acc.get("milieux", True),
            intersections=cfg_acc.get("intersections", True), sur_trait=cfg_acc.get("sur_trait", True),
            segments_max_intersections=int(cfg_acc.get("segments_max_intersections", 40)))
        self.accrochage_actif = bool(cfg_acc.get("actif", True))
        self._tolerance_px = float(cfg_acc.get("tolerance_pixels", 12))
        self._pas_contrainte = float(config["contrainte"].get("pas_angle_degres", 45))
        aff = config["affichage"]
        self._couleur = QColor(aff["couleur_mesures"])
        self._couleur_selection = QColor(aff["couleur_selection"])
        self._couleur_reference = QColor(aff["couleur_references"])
        self._couleur_apercu = QColor(aff["couleur_apercu"])
        self._taille_police = float(aff.get("taille_police_etiquettes", 9))

        # Fonctions fournies par la fenêtre
        self.formateur_apercu: Callable[[Outil, list[geo.Point]], str] | None = None  # valeur en direct
        self.style_annotation: Callable[[], Style] = Style                           # style des nouveaux tracés
        self.etiquette_mesure: Callable[[int, list[geo.Point]], str] | None = None   # étiquette pendant l'édition

        # --- Scène et réglages de la vue
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        # Mise à jour complète : indispensable pour les éléments à taille écran constante
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setBackgroundBrush(QColor("#3B3F45"))
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

        # --- Fond de page
        self._ombre = QGraphicsRectItem()
        self._ombre.setBrush(QColor(0, 0, 0, 90))
        self._ombre.setPen(QPen(Qt.PenStyle.NoPen))
        self._ombre.setZValue(-2)
        self._papier = QGraphicsRectItem()
        self._papier.setBrush(QColor("white"))
        self._papier.setPen(QPen(Qt.PenStyle.NoPen))
        self._papier.setZValue(-1)
        self._fond = QGraphicsPixmapItem()
        self._fond.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._fond.setZValue(0)
        self._detail = QGraphicsPixmapItem()
        self._detail.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._detail.setZValue(1)
        self._detail.hide()
        for item in (self._ombre, self._papier, self._fond, self._detail):
            self._scene.addItem(item)

        # --- Aperçus et marqueur
        self._apercu = QGraphicsPathItem()
        self._apercu.setZValue(50)
        self._scene.addItem(self._apercu)
        self._etiquette_apercu = Etiquette("", self._couleur_apercu, self._taille_police,
                                           decalage=DECALAGE_ETIQUETTE_APERCU)
        self._etiquette_apercu.hide()
        self._scene.addItem(self._etiquette_apercu)
        self._marqueur = MarqueurAccrochage()
        self._marqueur.hide()
        self._scene.addItem(self._marqueur)
        self._items_apercu_annotation: list[QGraphicsItem] = []

        # --- Éléments affichés
        self._elements: dict[int, ElementAffiche] = {}
        self._ordre_annotations: list[int] = []   # ordre de dessin (le dernier est au-dessus)
        self._items_element: dict[int, list[QGraphicsItem]] = {}
        self._items_references: list[QGraphicsItem] = []
        self._items_poignees: list[QGraphicsItem] = []
        self._rects_textes: dict[int, QRectF] = {}
        self._selection: set[int] = set()

        # --- État
        self._document: DocumentPDF | None = None
        self._numero_page = 0
        self._rect_page = QRectF()
        self._index: geo.IndexSegments | None = None
        self._zoom_fond = 1.0
        self._outil = Outil.NAVIGATION
        self._points: list[geo.Point] = []
        self._courant: geo.Point | None = None
        self._glisser_debut: geo.Point | None = None
        self._edition: Edition | None = None
        self._panoramique = False
        self._dernier_pan = QPointF()
        self._pos_appui = QPointF()
        self._espace = False

        # Rendu haute définition différé de la zone visible
        self._minuteur = QTimer(self)
        self._minuteur.setSingleShot(True)
        self._minuteur.setInterval(int(config["rendu"].get("delai_rendu_detail_ms", 150)))
        self._minuteur.timeout.connect(self._rendre_detail)
        self.horizontalScrollBar().valueChanged.connect(self._planifier_detail)
        self.verticalScrollBar().valueChanged.connect(self._planifier_detail)
        self._mettre_a_jour_curseur()

    # ==================================================================
    # Chargement d'une page
    # ==================================================================
    def charger_page(self, document: DocumentPDF, numero: int) -> None:
        """Affiche une page : rendu de fond, index des traits, cadrage."""
        self._document = document
        self._numero_page = numero
        largeur, hauteur = document.taille_page(numero)
        x0, y0 = document.origine_page(numero)
        self._rect_page = QRectF(x0, y0, largeur, hauteur)

        # Rendu de fond : résolution plafonnée pour borner la mémoire (plans A0)
        pixels_max = float(self._cfg["rendu"].get("pixels_max_fond", 16e6))
        zoom = min(float(self._cfg["rendu"].get("zoom_max_fond", 4.0)),
                   math.sqrt(pixels_max / max(largeur * hauteur, 1.0)))
        self._fond.setPixmap(QPixmap.fromImage(self._image(document.rendre(numero, zoom))))
        self._fond.setScale(1.0 / zoom)
        self._fond.setPos(x0, y0)
        self._zoom_fond = zoom
        self._detail.hide()
        self._papier.setRect(self._rect_page)
        self._ombre.setRect(self._rect_page.translated(largeur * 0.004, hauteur * 0.004))
        # Marge généreuse autour de la page pour zoomer près des bords
        self._scene.setSceneRect(self._rect_page.adjusted(-largeur, -hauteur, largeur, hauteur))

        segments = document.segments(numero)
        self._index = geo.IndexSegments(segments, max(largeur, hauteur) / 300.0)
        journal.info("Page %d affichée (fond ×%.2f, %d traits indexés)", numero + 1, zoom, len(segments))
        self.annuler_trace()
        self._edition = None
        self.ajuster()

    @staticmethod
    def _image(rendu: tuple[bytes, int, int, int]) -> QImage:
        donnees, largeur, hauteur, pas = rendu
        # copy() : l'image devient propriétaire de ses données
        return QImage(donnees, largeur, hauteur, pas, QImage.Format.Format_RGB888).copy()

    @property
    def nombre_traits(self) -> int:
        return len(self._index) if self._index else 0

    # ==================================================================
    # Zoom et rendu de détail
    # ==================================================================
    def echelle_vue(self) -> float:
        """Pixels écran par point PDF."""
        return self.transform().m11()

    def _px(self, pixels: float) -> float:
        """Conversion d'une distance écran (px) en distance de scène (pt)."""
        return pixels / max(self.echelle_vue(), 1e-9)

    def zone_visible(self) -> tuple[float, float, float, float]:
        """Partie de la page visible à l'écran (x0, y0, x1, y1), en pt."""
        visible = self.mapToScene(self.viewport().rect()).boundingRect().intersected(self._rect_page)
        if visible.isEmpty():
            visible = QRectF(self._rect_page)
        return (visible.left(), visible.top(), visible.right(), visible.bottom())

    def ajuster(self) -> None:
        """Cadre la page entière dans la fenêtre."""
        if self._rect_page.isEmpty():
            return
        self.fitInView(self._rect_page.adjusted(-10, -10, 10, 10), Qt.AspectRatioMode.KeepAspectRatio)
        self._apres_zoom()

    def cadrer(self, points: list[geo.Point]) -> None:
        """Zoome sur l'emprise d'un élément."""
        if not points:
            return
        x0, y0, x1, y1 = geo.boite_englobante(points)
        marge = max(x1 - x0, y1 - y0, 20.0) * 0.35
        self.fitInView(QRectF(x0 - marge, y0 - marge, x1 - x0 + 2 * marge, y1 - y0 + 2 * marge),
                       Qt.AspectRatioMode.KeepAspectRatio)
        self._apres_zoom()

    def zoomer(self, facteur: float, ancre_vue: QPointF | None = None) -> None:
        """Zoom autour d'un point de la vue (curseur) ou du centre."""
        actuel = self.echelle_vue()
        facteur = max(ZOOM_MIN / actuel, min(ZOOM_MAX / actuel, facteur))
        if ancre_vue is None:
            ancre_vue = QPointF(self.viewport().rect().center())
        avant = self.mapToScene(ancre_vue.toPoint())
        self.scale(facteur, facteur)
        apres = self.mapToScene(ancre_vue.toPoint())
        # Compensation pour garder le point sous le curseur immobile
        delta = apres - avant
        self.translate(delta.x(), delta.y())
        self._apres_zoom()

    def _apres_zoom(self) -> None:
        self._planifier_detail()
        # La poignée de rotation est placée à distance écran constante : on la recalcule
        if self._edition is None:
            self._afficher_poignees()

    def wheelEvent(self, evenement) -> None:  # noqa: N802
        crans = evenement.angleDelta().y() / 120.0
        if crans:
            self.zoomer(1.25 ** crans, evenement.position())
        evenement.accept()

    def resizeEvent(self, evenement) -> None:  # noqa: N802
        super().resizeEvent(evenement)
        self._planifier_detail()

    def _planifier_detail(self, *_args) -> None:
        if self._document is not None:
            self._minuteur.start()

    def _rendre_detail(self) -> None:
        """Rend la zone visible à la résolution de l'écran quand le fond devient flou."""
        if self._document is None:
            return
        besoin = self.echelle_vue() * self.viewport().devicePixelRatioF()
        if besoin <= self._zoom_fond * 1.05:
            self._detail.hide()
            return
        visible = self.mapToScene(self.viewport().rect()).boundingRect().intersected(self._rect_page)
        if visible.isEmpty():
            self._detail.hide()
            return
        zoom = besoin
        pixels_max = float(self._cfg["rendu"].get("pixels_max_detail", 12e6))
        surface = visible.width() * visible.height() * zoom * zoom
        if surface > pixels_max:
            zoom *= math.sqrt(pixels_max / surface)
        try:
            rendu = self._document.rendre(self._numero_page, zoom,
                                          (visible.left(), visible.top(), visible.right(), visible.bottom()))
        except Exception:
            journal.exception("Rendu de détail impossible")
            self._detail.hide()
            return
        self._detail.setPixmap(QPixmap.fromImage(self._image(rendu)))
        self._detail.setScale(1.0 / zoom)
        self._detail.setPos(visible.topLeft())
        self._detail.show()

    # ==================================================================
    # Outils de tracé
    # ==================================================================
    @property
    def outil(self) -> Outil:
        return self._outil

    def definir_outil(self, outil: Outil) -> None:
        if outil is self._outil:
            return
        self.annuler_trace()
        self._outil = outil
        self._marqueur.hide()
        self._mettre_a_jour_curseur()
        self._afficher_poignees()
        self.outil_change.emit(outil)

    def _mettre_a_jour_curseur(self, forme: Qt.CursorShape | None = None) -> None:
        if forme is not None:
            self.viewport().setCursor(forme)
        elif self._outil is Outil.NAVIGATION or self._espace:
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)

    def annuler_trace(self) -> None:
        self._points.clear()
        self._glisser_debut = None
        self._apercu.setPath(QPainterPath())
        self._etiquette_apercu.hide()
        self._effacer_apercu_annotation()

    def _effacer_apercu_annotation(self) -> None:
        for item in self._items_apercu_annotation:
            self._scene.removeItem(item)
        self._items_apercu_annotation.clear()

    def _afficher_apercu_annotation(self, type_annotation: TypeAnnotation, points: list[geo.Point]) -> None:
        """Aperçu fidèle (style courant) de l'annotation en cours de tracé."""
        self._effacer_apercu_annotation()
        if len(points) < 2 or (len(points) == 2 and geo.distance(points[0], points[-1]) < 1e-9):
            return
        apercu = Annotation(-1, type_annotation, self._numero_page, points, self.style_annotation())
        for item in items_annotation(apercu):
            item.setOpacity(0.7)
            item.setZValue(55)
            self._scene.addItem(item)
            self._items_apercu_annotation.append(item)

    def retirer_dernier_point(self) -> None:
        if self._points:
            self._points.pop()
            self._mettre_a_jour_apercu()

    def terminer_trace(self) -> bool:
        """Valide le tracé en cours ; retourne True si un élément a été créé."""
        minimum = POINTS_MINIMUM.get(self._outil, POINTS_FIXES.get(self._outil, 0))
        if not self._points or len(self._points) < minimum:
            return False
        points = list(self._points)
        self.annuler_trace()
        if self._outil is Outil.CALIBRATION:
            self.reference_tracee.emit(points)
        elif self._outil in ANNOTATION_PAR_OUTIL:
            self.annotation_tracee.emit(ANNOTATION_PAR_OUTIL[self._outil], points)
        else:
            self.mesure_terminee.emit(self._outil, points)
        return True

    def _ajouter_point(self, p: geo.Point) -> None:
        # Ignore un double-clic au même endroit
        if self._points and geo.distance(self._points[-1], p) < 1e-6:
            return
        self._points.append(p)
        fixe = POINTS_FIXES.get(self._outil)
        if fixe and len(self._points) >= fixe:
            self.terminer_trace()
        else:
            self._mettre_a_jour_apercu()

    # ==================================================================
    # Accrochage
    # ==================================================================
    def _sommets_accrochables(self, exclure: int | None = None) -> list[geo.Point]:
        """Sommets des éléments affichés (cibles d'accrochage), hors élément en cours d'édition."""
        resultat: list[geo.Point] = []
        for identifiant, element in self._elements.items():
            if identifiant == exclure:
                continue
            if element.est_annotation and element.annotation.type is not TypeAnnotation.TEXTE:
                resultat += element.annotation.poignees()
            elif not element.est_annotation:
                resultat += element.points
        return resultat

    def _point_souris(self, pos_vue: QPointF, modificateurs, contrainte: bool = True,
                      origine: geo.Point | None = None, exclure: int | None = None) -> tuple[geo.Point, str]:
        """Point de la scène après contrainte (Maj) ou accrochage (désactivé par Ctrl)."""
        s = self.mapToScene(pos_vue.toPoint())
        p = (s.x(), s.y())
        if origine is None and self._points:
            origine = self._points[-1]
        if contrainte and modificateurs & Qt.KeyboardModifier.ShiftModifier and origine is not None:
            return geo.contraindre_angle(origine, p, self._pas_contrainte), "contraint"
        if not self.accrochage_actif or modificateurs & Qt.KeyboardModifier.ControlModifier:
            return p, "libre"
        resultat = geo.accrocher(p, self._index, self._px(self._tolerance_px), self.options_accrochage,
                                 self._sommets_accrochables(exclure) + self._points)
        return resultat.point, resultat.type

    def _montrer_marqueur(self, p: geo.Point, nature: str) -> None:
        self._marqueur.setPos(QPointF(*p))
        self._marqueur.definir_type(nature if nature != "contraint" else "libre")
        self._marqueur.show()

    # ==================================================================
    # Souris et clavier
    # ==================================================================
    def mousePressEvent(self, evenement) -> None:  # noqa: N802
        bouton = evenement.button()
        pos = evenement.position()
        s = self.mapToScene(pos.toPoint())
        point = (s.x(), s.y())

        # --- Clic droit : termine / annule, retour à la navigation
        if bouton == Qt.MouseButton.RightButton:
            if self._edition is not None:
                self._annuler_edition()
            elif self._outil is not Outil.NAVIGATION:
                if self._outil in POINTS_MINIMUM:
                    self.terminer_trace()
                self.definir_outil(Outil.NAVIGATION)
            else:
                self.mesure_cliquee.emit(-1)
            evenement.accept()
            return

        # --- Navigation : poignées, déplacement d'éléments, sinon panoramique
        if bouton == Qt.MouseButton.LeftButton and self._outil is Outil.NAVIGATION and not self._espace:
            if self._clic_poignee(pos, evenement.modifiers(), point):
                evenement.accept()
                return
            identifiant = self._element_sous(point)
            if identifiant >= 0:
                if identifiant not in self._selection or len(self._selection) > 1:
                    self.mesure_cliquee.emit(identifiant)  # la fenêtre redessine : éléments recréés
                element = self._elements.get(identifiant)
                if element is not None:
                    self._commencer_edition(element, "deplacer", -1, point)
                evenement.accept()
                return

        # --- Annotations tracées par glisser
        if bouton == Qt.MouseButton.LeftButton and self._outil in OUTILS_GLISSER and not self._espace:
            p, _type = self._point_souris(pos, evenement.modifiers())
            self._glisser_debut = p
            self._courant = p  # évite de réutiliser une position antérieure si la souris ne bouge pas
            self._points = [p]
            evenement.accept()
            return
        if bouton == Qt.MouseButton.LeftButton and self._outil is Outil.TEXTE and not self._espace:
            p, _type = self._point_souris(pos, evenement.modifiers())
            self.texte_demande.emit(p)
            evenement.accept()
            return

        navigation = self._outil is Outil.NAVIGATION or self._espace
        if bouton == Qt.MouseButton.MiddleButton or (bouton == Qt.MouseButton.LeftButton and navigation):
            self._panoramique = True
            self._dernier_pan = pos
            self._pos_appui = pos
            self._mettre_a_jour_curseur(Qt.CursorShape.ClosedHandCursor)
            evenement.accept()
            return
        if bouton == Qt.MouseButton.LeftButton:
            p, _type = self._point_souris(pos, evenement.modifiers())
            self._ajouter_point(p)
            evenement.accept()
            return
        super().mousePressEvent(evenement)

    def mouseDoubleClickEvent(self, evenement) -> None:  # noqa: N802
        if evenement.button() != Qt.MouseButton.LeftButton:
            super().mouseDoubleClickEvent(evenement)
            return
        if self._outil in POINTS_MINIMUM:
            self.terminer_trace()
            evenement.accept()
            return
        if self._outil is Outil.NAVIGATION:
            self._edition = None
            s = self.mapToScene(evenement.position().toPoint())
            point = (s.x(), s.y())
            identifiant = self._element_sous(point)
            if identifiant >= 0:
                if not self._inserer_sommet(identifiant, point):
                    self.element_double_clic.emit(identifiant)
                evenement.accept()
                return
        super().mouseDoubleClickEvent(evenement)

    def mouseMoveEvent(self, evenement) -> None:  # noqa: N802
        pos = evenement.position()
        if self._edition is not None:
            self._maj_edition(pos, evenement.modifiers())
            evenement.accept()
            return
        if self._glisser_debut is not None:
            outil = self._outil
            carre = outil in (Outil.RECTANGLE, Outil.ELLIPSE)
            p, nature = self._point_souris(pos, evenement.modifiers(), contrainte=not carre)
            if carre and evenement.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Maj : carré / cercle inscrit
                d0 = self._glisser_debut
                cote = max(abs(p[0] - d0[0]), abs(p[1] - d0[1]))
                p = (d0[0] + math.copysign(cote, p[0] - d0[0]), d0[1] + math.copysign(cote, p[1] - d0[1]))
            self._courant = p
            self._montrer_marqueur(p, nature)
            self._afficher_apercu_annotation(ANNOTATION_PAR_OUTIL[outil], [self._glisser_debut, p])
            self.position_changee.emit(p[0], p[1], nature)
            evenement.accept()
            return
        if self._panoramique:
            delta = pos - self._dernier_pan
            self._dernier_pan = pos
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - delta.x()))
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - delta.y()))
            evenement.accept()
            return

        if self._outil is Outil.NAVIGATION and not self._espace:
            # Survol : le curseur indique ce qu'un glisser ferait
            s = self.mapToScene(pos.toPoint())
            point = (s.x(), s.y())
            if self._poignee_sous(pos) is not None:
                self._mettre_a_jour_curseur(Qt.CursorShape.PointingHandCursor)
            elif self._element_sous(point) >= 0:
                self._mettre_a_jour_curseur(Qt.CursorShape.SizeAllCursor)
            else:
                self._mettre_a_jour_curseur()
            self._marqueur.hide()
            self.position_changee.emit(point[0], point[1], "libre")
            super().mouseMoveEvent(evenement)
            return

        p, nature = self._point_souris(pos, evenement.modifiers())
        self._courant = p
        if not self._espace:
            self._montrer_marqueur(p, nature)
            self._mettre_a_jour_apercu()
        else:
            self._marqueur.hide()
        self.position_changee.emit(p[0], p[1], nature)
        super().mouseMoveEvent(evenement)

    def mouseReleaseEvent(self, evenement) -> None:  # noqa: N802
        if self._edition is not None and evenement.button() == Qt.MouseButton.LeftButton:
            edition = self._edition
            self._edition = None
            self._marqueur.hide()
            self._mettre_a_jour_curseur()
            if edition.modifie:
                angle = edition.angle if edition.element.est_annotation else None
                self.geometrie_modifiee.emit(edition.element.identifiant, list(edition.points), angle)
            evenement.accept()
            return
        if self._glisser_debut is not None and evenement.button() == Qt.MouseButton.LeftButton:
            debut, fin = self._glisser_debut, self._courant or self._glisser_debut
            type_annotation = ANNOTATION_PAR_OUTIL[self._outil]
            self.annuler_trace()
            # Un simple clic (moins de 3 pixels) ne crée rien
            if geo.distance(debut, fin) * self.echelle_vue() >= 3:
                self.annotation_tracee.emit(type_annotation, [debut, fin])
            evenement.accept()
            return
        if self._panoramique and evenement.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._panoramique = False
            self._mettre_a_jour_curseur()
            # Clic sans déplacement en navigation, sur le vide : désélection
            if (evenement.position() - self._pos_appui).manhattanLength() < 4 \
                    and self._outil is Outil.NAVIGATION and evenement.button() == Qt.MouseButton.LeftButton:
                self.mesure_cliquee.emit(-1)
            evenement.accept()
            return
        super().mouseReleaseEvent(evenement)

    def leaveEvent(self, evenement) -> None:  # noqa: N802
        self._marqueur.hide()
        super().leaveEvent(evenement)

    def keyPressEvent(self, evenement) -> None:  # noqa: N802
        touche = evenement.key()
        if touche == Qt.Key.Key_Escape:
            if self._edition is not None:
                self._annuler_edition()
            elif self._points or self._glisser_debut is not None:
                self.annuler_trace()
            else:
                self.definir_outil(Outil.NAVIGATION)
        elif touche == Qt.Key.Key_Backspace:
            self.retirer_dernier_point()
        elif touche in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.terminer_trace()
        elif touche == Qt.Key.Key_Space and not evenement.isAutoRepeat():
            self._espace = True
            self._marqueur.hide()
            self._mettre_a_jour_curseur()
        elif touche in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.zoomer(1.25)
        elif touche == Qt.Key.Key_Minus:
            self.zoomer(0.8)
        else:
            super().keyPressEvent(evenement)
            return
        evenement.accept()

    def keyReleaseEvent(self, evenement) -> None:  # noqa: N802
        if evenement.key() == Qt.Key.Key_Space and not evenement.isAutoRepeat():
            self._espace = False
            self._mettre_a_jour_curseur()
            evenement.accept()
            return
        super().keyReleaseEvent(evenement)

    # ==================================================================
    # Aperçu du tracé en cours
    # ==================================================================
    def _mettre_a_jour_apercu(self) -> None:
        if self._outil is Outil.NAVIGATION or not self._points or self._courant is None:
            self._apercu.setPath(QPainterPath())
            self._etiquette_apercu.hide()
            return
        points = self._points + [self._courant]
        if self._outil in (Outil.POLYLIGNE, Outil.POLYGONE):
            self._apercu.setPath(QPainterPath())
            self._afficher_apercu_annotation(ANNOTATION_PAR_OUTIL[self._outil], points)
            return
        chemin = QPainterPath(QPointF(*points[0]))
        for p in points[1:]:
            chemin.lineTo(QPointF(*p))
        if self._outil is Outil.SURFACE and len(points) >= 3:
            chemin.lineTo(QPointF(*points[0]))
        if self._outil is Outil.DISTANCE_XY and len(points) == 2:
            # Aperçu du triangle de décomposition ΔX / ΔY
            coin = ann.coin_decomposition(points[0], points[1])
            chemin.moveTo(QPointF(*points[0]))
            chemin.lineTo(QPointF(*coin))
            chemin.lineTo(QPointF(*points[1]))
        couleur = self._couleur_reference if self._outil is Outil.CALIBRATION else self._couleur_apercu
        self._apercu.setPen(stylo_cosmetique(couleur, 2.0, pointille=True))
        if self._outil is Outil.SURFACE:
            remplissage = QColor(couleur)
            remplissage.setAlpha(40)
            self._apercu.setBrush(QBrush(remplissage))
        else:
            self._apercu.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._apercu.setPath(chemin)
        if self.formateur_apercu:
            self._etiquette_apercu.definir_texte(self.formateur_apercu(self._outil, points))
            self._etiquette_apercu.setPos(QPointF(*self._courant))
            self._etiquette_apercu.show()

    # ==================================================================
    # Affichage des éléments enregistrés
    # ==================================================================
    def afficher_mesures(self, mesures: list[tuple[int, str, list[geo.Point], str]],
                         references: list[tuple[list[geo.Point], str]],
                         selection: set[int], annotations: list[Annotation] | None = None) -> None:
        """Redessine mesures (id, type, points, étiquette), cotes de référence et annotations."""
        for items in self._items_element.values():
            for item in items:
                self._scene.removeItem(item)
        for item in self._items_references:
            self._scene.removeItem(item)
        self._items_element.clear()
        self._items_references.clear()
        self._rects_textes.clear()
        self._elements.clear()
        self._selection = set(selection)

        self._ordre_annotations = []
        for a in annotations or []:
            self._elements[a.identifiant] = ElementAffiche(a.identifiant, a.type.value, list(a.points),
                                                          annotation=a)
            self._ordre_annotations.append(a.identifiant)
        for identifiant, type_mesure, points, texte in mesures:
            self._elements[identifiant] = ElementAffiche(identifiant, type_mesure, list(points), texte)
        for identifiant, element in self._elements.items():
            self._items_element[identifiant] = self._construire(element, identifiant in self._selection)
        for points, texte in references:
            for item in items_mesure("référence", points, texte, self._couleur_reference, 2.0,
                                     self._taille_police, pointille=True):
                self._scene.addItem(item)
                self._items_references.append(item)
        self._afficher_poignees()

    def _construire(self, element: ElementAffiche, selectionne: bool) -> list[QGraphicsItem]:
        """Crée et place dans la scène les éléments graphiques d'une mesure ou d'une annotation."""
        if element.est_annotation:
            a = element.annotation
            items = items_annotation(a)
            rect_texte = None
            if a.type is TypeAnnotation.TEXTE:
                rect_texte = items[-1].rect
                self._rects_textes[a.identifiant] = rect_texte
            if selectionne:
                items.append(cadre_selection(a, rect_texte, self._couleur_selection))
        else:
            couleur = self._couleur_selection if selectionne else self._couleur
            items = items_mesure(element.type, element.points, element.texte, couleur,
                                 3.0 if selectionne else 2.0, self._taille_police)
        for item in items:
            self._scene.addItem(item)
        return items

    def _remplacer_rendu(self, element: ElementAffiche) -> None:
        """Redessine un seul élément (édition en direct)."""
        for item in self._items_element.pop(element.identifiant, []):
            self._scene.removeItem(item)
        self._items_element[element.identifiant] = self._construire(element, element.identifiant in self._selection)

    # ==================================================================
    # Poignées d'édition
    # ==================================================================
    def _element_edite(self) -> ElementAffiche | None:
        """Élément dont on affiche les poignées : sélection unique, outil Naviguer."""
        if self._outil is not Outil.NAVIGATION or len(self._selection) != 1:
            return None
        return self._elements.get(next(iter(self._selection)))

    def _poignees_de(self, element: ElementAffiche) -> tuple[list[geo.Point], geo.Point | None, geo.Point | None]:
        """(poignées de sommets, poignée de rotation, point d'attache de la tige de rotation)."""
        if not element.est_annotation:
            return list(element.points), None, None
        a = element.annotation
        sommets = a.poignees()
        if a.type not in ann.TYPES_ORIENTABLES:
            return sommets, None, None
        d = self._px(DISTANCE_POIGNEE_ROTATION_PX)
        if a.type in (TypeAnnotation.RECTANGLE, TypeAnnotation.ELLIPSE):
            x0, y0, x1, y1 = a.boite()
            c = ((x0 + x1) / 2, (y0 + y1) / 2)
            haut = (c[0], min(y0, y1))
            # Au-dessus du bord supérieur, dans le repère tourné de la forme
            return (sommets, geo.tourner((haut[0], haut[1] - d), c, a.angle), geo.tourner(haut, c, a.angle))
        p0, p1 = a.points[0], a.points[1]
        m = geo.milieu(p0, p1)
        longueur = max(geo.distance(p0, p1), 1e-9)
        perpendiculaire = (-(p1[1] - p0[1]) / longueur, (p1[0] - p0[0]) / longueur)
        return (sommets, (m[0] + perpendiculaire[0] * d, m[1] + perpendiculaire[1] * d), m)

    def _effacer_poignees(self) -> None:
        for item in self._items_poignees:
            self._scene.removeItem(item)
        self._items_poignees.clear()

    def _afficher_poignees(self, element: ElementAffiche | None = None) -> None:
        self._effacer_poignees()
        element = element or self._element_edite()
        if element is None:
            return
        sommets, rotation, attache = self._poignees_de(element)
        for p in sommets:
            poignee = Poignee(self._couleur_selection)
            poignee.setPos(QPointF(*p))
            self._scene.addItem(poignee)
            self._items_poignees.append(poignee)
        if rotation is not None:
            tige = QGraphicsLineItem(attache[0], attache[1], rotation[0], rotation[1])
            tige.setPen(stylo_cosmetique(self._couleur_selection, 1.0))
            tige.setZValue(74)
            poignee = Poignee(self._couleur_selection, rotation=True)
            poignee.setPos(QPointF(*rotation))
            for item in (tige, poignee):
                self._scene.addItem(item)
                self._items_poignees.append(item)

    def _poignee_sous(self, pos_vue: QPointF) -> tuple[str, int] | None:
        """("rotation", -1) ou ("sommet", indice) sous le curseur, sinon None."""
        element = self._element_edite()
        if element is None:
            return None
        sommets, rotation, _attache = self._poignees_de(element)

        def proche(p: geo.Point) -> float:
            v = self.mapFromScene(QPointF(*p))
            return math.hypot(v.x() - pos_vue.x(), v.y() - pos_vue.y())

        if rotation is not None and proche(rotation) <= RAYON_POIGNEE_PX:
            return ("rotation", -1)
        distances = [(proche(p), i) for i, p in enumerate(sommets)]
        if distances:
            d, i = min(distances)
            if d <= RAYON_POIGNEE_PX:
                return ("sommet", i)
        return None

    def _clic_poignee(self, pos_vue: QPointF, modificateurs, point: geo.Point) -> bool:
        cible = self._poignee_sous(pos_vue)
        element = self._element_edite()
        if cible is None or element is None:
            return False
        nature, indice = cible
        if nature == "sommet" and modificateurs & Qt.KeyboardModifier.ControlModifier:
            self._supprimer_sommet(element, indice)
            return True
        self._commencer_edition(element, nature, indice, point)
        return True

    # ==================================================================
    # Édition : déplacement, sommets, rotation
    # ==================================================================
    def _commencer_edition(self, element: ElementAffiche, nature: str, indice: int, point: geo.Point) -> None:
        a0 = element.annotation.copie() if element.est_annotation else None
        edition = Edition(element, nature, indice, point, list(element.points), a0,
                          points=list(element.points), angle=a0.angle if a0 else 0.0)
        if nature == "rotation" and a0 is not None:
            edition.centre = a0.centre_geometrique()
            edition.angle_souris0 = geo.orientation_degres(edition.centre, point)
        self._edition = edition
        curseurs = {"deplacer": Qt.CursorShape.SizeAllCursor, "sommet": Qt.CursorShape.CrossCursor,
                    "rotation": Qt.CursorShape.ClosedHandCursor}
        self._mettre_a_jour_curseur(curseurs[nature])

    def _maj_edition(self, pos_vue: QPointF, modificateurs) -> None:
        e = self._edition
        s = self.mapToScene(pos_vue.toPoint())
        point = (s.x(), s.y())
        maj = bool(modificateurs & Qt.KeyboardModifier.ShiftModifier)
        a = e.annotation0.copie() if e.annotation0 is not None else None

        if e.nature == "deplacer":
            dx, dy = point[0] - e.depart[0], point[1] - e.depart[1]
            if maj:
                dx, dy = (dx, 0.0) if abs(dx) >= abs(dy) else (0.0, dy)
            if abs(dx) * self.echelle_vue() < 1 and abs(dy) * self.echelle_vue() < 1 and not e.modifie:
                return  # simple clic : pas de déplacement parasite
            if a is not None:
                a.deplacer(dx, dy)
                e.points, e.angle = a.points, a.angle
            else:
                e.points = [(x + dx, y + dy) for x, y in e.points0]
            self.position_changee.emit(point[0], point[1], "libre")

        elif e.nature == "sommet":
            origine = self._voisin(e, e.indice)
            q, nature = self._point_souris(pos_vue, modificateurs, origine=origine, exclure=e.element.identifiant)
            self._montrer_marqueur(q, nature)
            if a is not None:
                a.deplacer_poignee(e.indice, q)
                e.points, e.angle = a.points, a.angle
            else:
                e.points = list(e.points0)
                e.points[e.indice] = q
            self.position_changee.emit(q[0], q[1], nature)

        else:  # rotation
            if a is None:
                return
            delta = geo.orientation_degres(e.centre, point) - e.angle_souris0
            orientation0 = e.annotation0.orientation or 0.0
            cible = orientation0 + delta
            if maj:
                cible = round(cible / PAS_ROTATION_CONTRAINTE) * PAS_ROTATION_CONTRAINTE
            a.definir_orientation(cible)
            e.points, e.angle = a.points, a.angle
            self._montrer_marqueur(point, "libre")

        e.modifie = True
        self._rendu_temporaire(e)

    def _voisin(self, e: Edition, indice: int) -> geo.Point | None:
        """Point de référence pour la contrainte d'angle (Maj) lors du déplacement d'un sommet."""
        if e.annotation0 is not None and e.annotation0.type in (TypeAnnotation.RECTANGLE, TypeAnnotation.ELLIPSE,
                                                                TypeAnnotation.CERCLE):
            return None
        pts = e.points0
        if len(pts) < 2:
            return None
        return pts[indice - 1] if indice > 0 else pts[1]

    def _rendu_temporaire(self, e: Edition) -> None:
        """Affiche l'élément avec sa géométrie en cours de modification."""
        element = e.element
        if element.est_annotation:
            a = e.annotation0.copie()
            a.points, a.angle = list(e.points), e.angle
            temporaire = ElementAffiche(element.identifiant, element.type, list(e.points), annotation=a)
        else:
            texte = self.etiquette_mesure(element.identifiant, e.points) if self.etiquette_mesure else element.texte
            temporaire = ElementAffiche(element.identifiant, element.type, list(e.points), texte)
        self._remplacer_rendu(temporaire)
        self._afficher_poignees(temporaire)

    def _annuler_edition(self) -> None:
        e = self._edition
        self._edition = None
        if e is not None:
            self._remplacer_rendu(e.element)
            self._afficher_poignees()
        self._marqueur.hide()
        self._mettre_a_jour_curseur()

    def _inserer_sommet(self, identifiant: int, point: geo.Point) -> bool:
        """Double-clic sur un côté : insère un sommet au point projeté. Retourne True si inséré."""
        element = self._elements.get(identifiant)
        if element is None or element.type not in SOMMETS_MODIFIABLES:
            return False
        pts = element.points
        cotes = list(range(len(pts) - 1)) + ([len(pts) - 1] if element.type in TYPES_FERMES else [])
        tolerance = self._px(self._tolerance_px)
        meilleur = None
        for i in cotes:
            a, b = pts[i], pts[(i + 1) % len(pts)]
            q, t = geo.projection_sur_segment(point, a, b)
            d = geo.distance(point, q)
            if d <= tolerance and 0.02 < t < 0.98 and (meilleur is None or d < meilleur[0]):
                meilleur = (d, i, q)
        if meilleur is None:
            return False
        _d, i, q = meilleur
        nouveaux = pts[:i + 1] + [q] + pts[i + 1:]
        angle = element.annotation.angle if element.est_annotation else None
        self.geometrie_modifiee.emit(identifiant, nouveaux, angle)
        return True

    def _supprimer_sommet(self, element: ElementAffiche, indice: int) -> None:
        minimum = SOMMETS_MODIFIABLES.get(element.type)
        if minimum is None or len(element.points) <= minimum:
            return
        nouveaux = element.points[:indice] + element.points[indice + 1:]
        angle = element.annotation.angle if element.est_annotation else None
        self.geometrie_modifiee.emit(element.identifiant, nouveaux, angle)

    # ==================================================================
    # Sélection au clic
    # ==================================================================
    def _element_sous(self, p: geo.Point) -> int:
        """Annotation sous le curseur (la dernière posée est au-dessus), sinon mesure, sinon -1."""
        tolerance = self._px(self._tolerance_px)
        for identifiant in reversed(self._ordre_annotations):
            element = self._elements.get(identifiant)
            if element is None:
                continue
            a = element.annotation
            if identifiant in self._rects_textes:
                if self._rects_textes[identifiant].adjusted(-tolerance, -tolerance, tolerance, tolerance) \
                        .contains(QPointF(*p)):
                    return identifiant
            elif a.distance(p) <= tolerance + a.style.epaisseur / 2:
                return identifiant
        return self._mesure_sous(p, tolerance)

    def _mesure_sous(self, p: geo.Point, tolerance: float) -> int:
        """Mesure la plus proche du clic, sinon surface contenant le point, sinon -1."""
        meilleur, distance_min = -1, tolerance
        surfaces = []
        for identifiant, element in self._elements.items():
            if element.est_annotation:
                continue
            points = element.points
            cotes = list(zip(points, points[1:]))
            if element.type == "surface" and len(points) > 2:
                cotes.append((points[-1], points[0]))
                if ann.point_dans_polygone(p, points):
                    surfaces.append((geo.aire_polygone(points), identifiant))
            for a, b in cotes:
                q, _t = geo.projection_sur_segment(p, a, b)
                d = geo.distance(p, q)
                if d < distance_min:
                    meilleur, distance_min = identifiant, d
        if meilleur == -1 and surfaces:
            meilleur = min(surfaces)[1]  # la plus petite surface contenant le point
        return meilleur

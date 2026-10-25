"""Accès au PDF via PyMuPDF : rendu raster, extraction des traits vectoriels, texte.

Les pages tournées (/Rotate) sont normalisées en mémoire (le fichier n'est
jamais modifié) : rendu, traits et texte partagent ainsi un repère unique.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from mesureplan import geometrie as geo
from mesureplan.echelle import DetectionEchelle, detecter_echelle

journal = logging.getLogger(__name__)

# Nombre de segments utilisés pour discrétiser une courbe de Bézier
PAS_BEZIER = 8
# Segments plus courts que ceci (en pt) ignorés : bruit de tracé
LONGUEUR_MIN_PT = 0.05


def _xy(p: Any) -> geo.Point:
    """Accepte un pymupdf.Point (attributs x, y) ou un tuple."""
    if hasattr(p, "x"):
        return (float(p.x), float(p.y))
    return (float(p[0]), float(p[1]))


def segments_depuis_dessins(dessins: Iterable[dict]) -> list[geo.Segment]:
    """Convertit la sortie de Page.get_drawings() en segments annotés.

    Fonction pure, testable sans PDF. Éléments gérés :
      « l » ligne, « c » Bézier cubique, « re » rectangle, « qu » quadrilatère.
    """
    segments: list[geo.Segment] = []

    def ajouter(a: geo.Point, b: geo.Point, drapeaux: int) -> None:
        if geo.distance(a, b) >= LONGUEUR_MIN_PT:
            segments.append((a, b, drapeaux))

    for dessin in dessins:
        for element in dessin.get("items", ()):
            nature = element[0]
            if nature == "l":
                ajouter(_xy(element[1]), _xy(element[2]), geo.SEGMENT_COMPLET)
            elif nature == "c":
                # Courbe : seules ses deux vraies extrémités sont des points d'accrochage
                points = geo.aplatir_bezier(*(_xy(p) for p in element[1:5]), pas=PAS_BEZIER)
                dernier = len(points) - 2
                for i in range(len(points) - 1):
                    drapeaux = (geo.EXTREMITE_A if i == 0 else 0) | (geo.EXTREMITE_B if i == dernier else 0)
                    ajouter(points[i], points[i + 1], drapeaux)
            elif nature == "re":
                r = element[1]
                coins = [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)] if hasattr(r, "x0") \
                    else [(r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3])]
                for i in range(4):
                    ajouter(coins[i], coins[(i + 1) % 4], geo.SEGMENT_COMPLET)
            elif nature == "qu":
                q = element[1]
                coins = [_xy(q.ul), _xy(q.ur), _xy(q.lr), _xy(q.ll)] if hasattr(q, "ul") \
                    else [_xy(p) for p in q]
                for i in range(4):
                    ajouter(coins[i], coins[(i + 1) % 4], geo.SEGMENT_COMPLET)
    return segments


class DocumentPDF:
    """Document PDF ouvert en lecture, avec caches par page."""

    def __init__(self, chemin: Path) -> None:
        import pymupdf  # import local : le reste du paquet reste testable sans PyMuPDF

        self._pymupdf = pymupdf
        self.chemin = Path(chemin)
        self._doc = pymupdf.open(self.chemin)
        if self._doc.needs_pass:
            raise PermissionError("PDF protégé par mot de passe : non pris en charge")
        self._cache_segments: dict[int, list[geo.Segment]] = {}
        self._cache_detection: dict[int, DetectionEchelle | None] = {}

        # Normalisation des pages tournées, en mémoire uniquement
        for page in self._doc:
            if page.rotation:
                journal.info("Page %d tournée de %d° : normalisation en mémoire", page.number + 1, page.rotation)
                page.remove_rotation()
        journal.info("PDF ouvert : %s (%d pages)", self.chemin, self.nombre_pages)

    @property
    def nombre_pages(self) -> int:
        return self._doc.page_count

    def taille_page(self, numero: int) -> tuple[float, float]:
        """Largeur et hauteur de la page en points."""
        r = self._doc[numero].rect
        return (r.width, r.height)

    def origine_page(self, numero: int) -> tuple[float, float]:
        """Coin supérieur gauche de la page (non nul si la MediaBox est décalée)."""
        r = self._doc[numero].rect
        return (r.x0, r.y0)

    def rendre(self, numero: int, zoom: float,
               zone: tuple[float, float, float, float] | None = None) -> tuple[bytes, int, int, int]:
        """Rend la page (ou une zone) en RGB ; retourne (octets, largeur, hauteur, pas de ligne)."""
        page = self._doc[numero]
        matrice = self._pymupdf.Matrix(zoom, zoom)
        clip = self._pymupdf.Rect(*zone) if zone else None
        pix = page.get_pixmap(matrix=matrice, clip=clip, alpha=False)
        return bytes(pix.samples), pix.width, pix.height, pix.stride

    def segments(self, numero: int) -> list[geo.Segment]:
        """Traits vectoriels de la page (mis en cache)."""
        if numero not in self._cache_segments:
            try:
                dessins = self._doc[numero].get_drawings()
                self._cache_segments[numero] = segments_depuis_dessins(dessins)
            except Exception:
                journal.exception("Extraction des traits impossible, page %d", numero + 1)
                self._cache_segments[numero] = []
            journal.info("Page %d : %d segments vectoriels", numero + 1, len(self._cache_segments[numero]))
        return self._cache_segments[numero]

    def detection_echelle(self, numero: int) -> DetectionEchelle | None:
        """Échelle lue dans le texte de la page (cartouche), si elle est trouvée."""
        if numero not in self._cache_detection:
            try:
                texte = self._doc[numero].get_text("text")
                self._cache_detection[numero] = detecter_echelle(texte)
            except Exception:
                journal.exception("Lecture du texte impossible, page %d", numero + 1)
                self._cache_detection[numero] = None
        return self._cache_detection[numero]

    def fermer(self) -> None:
        self._doc.close()

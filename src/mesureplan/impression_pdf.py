"""Génération du PDF d'impression à l'échelle (PyMuPDF), vectoriel.

Chaque feuille reçoit la portion de plan correspondante (show_pdf_page :
le dessin reste vectoriel, donc net à toute échelle) ainsi que :
  - des repères d'angle et les lignes de recouvrement (mosaïque) ;
  - une légende (fichier, page, échelle, format, repère de feuille) ;
  - une barre d'échelle graduée ;
  - un segment de contrôle de 100 mm pour vérifier que l'imprimante n'a pas
    redimensionné la page.
Une page « plan d'assemblage » précède la mosaïque quand il y a plusieurs feuilles.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from mesureplan import export_pdf
from mesureplan.annotations import Annotation, texte_pdf
from mesureplan.impression import PT_PAR_MM, PlanImpression, Tuile, barre_echelle, nom_tuile

journal = logging.getLogger(__name__)

NOIR = (0.0, 0.0, 0.0)
GRIS = (0.45, 0.45, 0.45)
BLEU = (0.12, 0.47, 0.82)
TAILLE_LEGENDE = 7.0


@dataclass
class OptionsImpression:
    """Repères ajoutés aux feuilles."""

    barre_echelle: bool = True
    segment_controle: bool = True
    reperes_assemblage: bool = True
    plan_assemblage: bool = True


def generer(source: Path, sortie: Path, numero_page: int, plan: PlanImpression,
            par_page: dict[int, list[Annotation]], titre: str, options: OptionsImpression) -> int:
    """Écrit le PDF d'impression ; retourne le nombre de pages produites."""
    import pymupdf

    if Path(source).resolve() == Path(sortie).resolve():
        raise ValueError("Le fichier d'impression doit être différent du plan d'origine.")
    # Plan + mesures/annotations incrustés, rechargé depuis des octets : source figée pour show_pdf_page
    doc_annote, compteurs = export_pdf.document_annote(source, par_page, export_pdf.MODE_INCRUSTE)
    try:
        source_figee = pymupdf.open("pdf", doc_annote.tobytes())
    finally:
        doc_annote.close()
    if compteurs["échecs"]:
        journal.warning("%d élément(s) non dessiné(s) sur le plan imprimé", compteurs["échecs"])

    sortie_doc = pymupdf.open()
    try:
        if plan.nombre_feuilles > 1 and options.plan_assemblage:
            _page_assemblage(pymupdf, sortie_doc, source_figee, numero_page, plan, titre)
        for indice, tuile in enumerate(plan.tuiles, start=1):
            page = sortie_doc.new_page(width=plan.largeur_feuille, height=plan.hauteur_feuille)
            page.show_pdf_page(pymupdf.Rect(*tuile.destination), source_figee, numero_page,
                               clip=pymupdf.Rect(*tuile.source))
            _reperes(pymupdf, page, plan, tuile, indice, titre, options)
        sortie_doc.set_metadata({"title": f"{titre} — impression 1:{plan.denominateur:g}",
                                 "creator": "MesurePlan", "producer": "MesurePlan / PyMuPDF"})
        nombre = sortie_doc.page_count
        sortie_doc.save(sortie, garbage=3, deflate=True)
    finally:
        sortie_doc.close()
        source_figee.close()
    journal.info("PDF d'impression %s : %d page(s), %s, 1:%g", sortie, nombre, plan.format, plan.denominateur)
    return nombre


# ---------------------------------------------------------------------------
# Repères d'une feuille
# ---------------------------------------------------------------------------

def _tronquer(pymupdf, texte: str, largeur_max: float, taille: float) -> str:
    """Raccourcit un texte (avec « … ») pour qu'il tienne dans la largeur donnée."""
    if pymupdf.get_text_length(texte, fontname="helv", fontsize=taille) <= largeur_max:
        return texte
    while texte and pymupdf.get_text_length(texte + "...", fontname="helv", fontsize=taille) > largeur_max:
        texte = texte[:-1]
    return texte + "..."


def _texte(pymupdf, page, x: float, y: float, texte: str, taille: float = TAILLE_LEGENDE,
           couleur=NOIR, gras: bool = False) -> None:
    page.insert_text(pymupdf.Point(x, y), texte, fontsize=taille, fontname="hebo" if gras else "helv",
                     color=couleur)


def _reperes(pymupdf, page, plan: PlanImpression, t: Tuile, indice: int, titre: str,
             options: OptionsImpression) -> None:
    P = pymupdf.Point  # noqa: N806
    x0, y0, x1, y1 = t.destination
    mosaique = plan.nombre_feuilles > 1
    forme = page.new_shape()

    # --- Repères d'angle de la zone imprimée (aide au découpage et à l'alignement)
    if options.reperes_assemblage:
        longueur = 5 * PT_PAR_MM
        for cx, cy, sx, sy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
            forme.draw_line(P(cx, cy), P(cx + sx * longueur, cy))
            forme.draw_line(P(cx, cy), P(cx, cy + sy * longueur))
        forme.finish(color=GRIS, width=0.4)

    # --- Lignes de recouvrement : la feuille voisine reprend la bande située au-delà
    if mosaique and options.reperes_assemblage:
        r = plan.recouvrement
        if t.colonne < plan.colonnes - 1:
            forme.draw_line(P(x1 - r, y0), P(x1 - r, y1))
        if t.ligne < plan.lignes - 1:
            forme.draw_line(P(x0, y1 - r), P(x1, y1 - r))
        forme.finish(color=BLEU, width=0.5, dashes="[4 3] 0", stroke_opacity=0.8)
    forme.commit()

    if mosaique and options.reperes_assemblage:
        if t.colonne < plan.colonnes - 1:
            voisin = nom_tuile(Tuile(t.ligne, t.colonne + 1, t.source, t.destination))
            _texte(pymupdf, page, x1 - plan.recouvrement + 2, y0 + 9, f"> {voisin}", 6.5, BLEU)
        if t.ligne < plan.lignes - 1:
            voisin = nom_tuile(Tuile(t.ligne + 1, t.colonne, t.source, t.destination))
            _texte(pymupdf, page, x0 + 2, y1 - plan.recouvrement + 8, f"v {voisin}", 6.5, BLEU)

    # --- Pied de page : légende à gauche, barre d'échelle à droite, contrôle 100 mm dessous
    ux0, _uy0, ux1, uy1 = plan.zone_utile
    haut_pied = uy1 + 2.5 * PT_PAR_MM
    largeur_utile = ux1 - ux0
    longueur_max_barre = min(60.0, largeur_utile / PT_PAR_MM / 3)
    longueur_m, divisions, longueur_mm = barre_echelle(plan.denominateur, longueur_max_barre)
    largeur_barre = longueur_mm * PT_PAR_MM if options.barre_echelle else 0.0
    largeur_texte = largeur_utile - largeur_barre - 8 * PT_PAR_MM

    repere = nom_tuile(t) if mosaique else ""
    ligne1 = f"{titre} — Échelle 1:{plan.denominateur:g} — {plan.format} {plan.orientation}"
    ligne2 = (f"Feuille {repere} ({indice}/{plan.nombre_feuilles}) — " if mosaique else "") + \
        "Imprimer à 100 % (taille réelle), sans « ajuster à la page »"
    for i, ligne in enumerate((ligne1, ligne2)):
        texte = _tronquer(pymupdf, texte_pdf(ligne), largeur_texte, TAILLE_LEGENDE)
        _texte(pymupdf, page, ux0, haut_pied + i * 9, texte, gras=(i == 0))

    if options.barre_echelle:
        _barre(pymupdf, page, ux1 - largeur_barre, haut_pied - 5, largeur_barre, longueur_m, divisions)

    if options.segment_controle and largeur_utile >= 110 * PT_PAR_MM:
        y = haut_pied + 21
        controle = page.new_shape()
        controle.draw_line(P(ux0, y), P(ux0 + 100 * PT_PAR_MM, y))
        for x in (ux0, ux0 + 100 * PT_PAR_MM):
            controle.draw_line(P(x, y - 3), P(x, y + 3))
        controle.finish(color=NOIR, width=0.5)
        controle.commit()
        _texte(pymupdf, page, ux0 + 100 * PT_PAR_MM + 6, y + 2.3,
               "Contrôle : ce segment doit mesurer exactement 100 mm", 6.0, GRIS)


def _barre(pymupdf, page, x: float, y: float, largeur: float, longueur_m: float, divisions: int) -> None:
    """Barre d'échelle à cases alternées noir/blanc, graduée en mètres."""
    hauteur = 2.2 * PT_PAR_MM
    pas = largeur / divisions
    forme = page.new_shape()
    for i in range(divisions):
        forme.draw_rect(pymupdf.Rect(x + i * pas, y, x + (i + 1) * pas, y + hauteur))
        forme.finish(color=NOIR, fill=NOIR if i % 2 == 0 else (1, 1, 1), width=0.4)
    forme.commit()
    for i in (0, divisions // 2, divisions) if divisions % 2 == 0 else (0, divisions):
        valeur = longueur_m * i / divisions
        etiquette = f"{valeur:g}".replace(".", ",") + (" m" if i == divisions else "")
        largeur_etiquette = pymupdf.get_text_length(etiquette, fontname="helv", fontsize=6)
        position = x + i * pas - (largeur_etiquette / 2 if i < divisions else largeur_etiquette - 3)
        _texte(pymupdf, page, position, y + hauteur + 7, etiquette, 6.0)


# ---------------------------------------------------------------------------
# Plan d'assemblage
# ---------------------------------------------------------------------------

def _page_assemblage(pymupdf, doc, source, numero_page: int, plan: PlanImpression, titre: str) -> None:
    """Vue réduite de la zone avec le quadrillage des feuilles et leurs repères (A1, A2, B1…)."""
    page = doc.new_page(width=plan.largeur_feuille, height=plan.hauteur_feuille)
    ux0, uy0, ux1, uy1 = plan.zone_utile
    zx0, zy0, zx1, zy1 = plan.zone
    haut = uy0 + 22  # place pour le titre
    reduction = min((ux1 - ux0) / (zx1 - zx0), (uy1 - haut) / (zy1 - zy0))
    largeur, hauteur = (zx1 - zx0) * reduction, (zy1 - zy0) * reduction
    ox = ux0 + ((ux1 - ux0) - largeur) / 2
    oy = haut
    page.show_pdf_page(pymupdf.Rect(ox, oy, ox + largeur, oy + hauteur), source, numero_page,
                       clip=pymupdf.Rect(*plan.zone))
    _texte(pymupdf, page, ux0, uy0 + 8,
           texte_pdf(f"Plan d'assemblage — {titre}"), 11, gras=True)
    _texte(pymupdf, page, ux0, uy0 + 19,
           texte_pdf(f"{plan.nombre_feuilles} feuilles {plan.format} {plan.orientation} "
                                    f"({plan.lignes} × {plan.colonnes}) à l'échelle 1:{plan.denominateur:g} — "
                                    "cette page de repérage n'est pas à l'échelle"), 7.5, GRIS)
    forme = page.new_shape()
    for t in plan.tuiles:
        sx0, sy0, sx1, sy1 = t.source
        forme.draw_rect(pymupdf.Rect(ox + (sx0 - zx0) * reduction, oy + (sy0 - zy0) * reduction,
                                     ox + (sx1 - zx0) * reduction, oy + (sy1 - zy0) * reduction))
    forme.finish(color=BLEU, width=0.8, fill=BLEU, fill_opacity=0.06)
    forme.commit()
    for t in plan.tuiles:
        sx0, sy0, sx1, sy1 = t.source
        cx = ox + ((sx0 + sx1) / 2 - zx0) * reduction
        cy = oy + ((sy0 + sy1) / 2 - zy0) * reduction
        nom = nom_tuile(t)
        taille = max(8.0, min(28.0, (sx1 - sx0) * reduction / 4))
        largeur_nom = pymupdf.get_text_length(nom, fontname="hebo", fontsize=taille)
        _texte(pymupdf, page, cx - largeur_nom / 2, cy + taille / 3, nom, taille, BLEU, gras=True)

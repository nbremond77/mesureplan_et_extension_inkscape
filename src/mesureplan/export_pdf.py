"""Export d'une copie du PDF enrichie des annotations et des mesures.

Deux modes :
  « incrusté »    : dessin ajouté au contenu des pages — rendu identique dans
                    toutes les visionneuses, mais non modifiable ensuite ;
  « annotations » : objets d'annotation PDF standard (ligne, rectangle,
                    ellipse, polygone, texte libre) — déplaçables / supprimables
                    dans Okular, Acrobat, Xournal++… Tout objet qu'il est impossible
                    de créer ainsi est incrusté à la place (et journalisé).

Le fichier source n'est jamais modifié. Les pages tournées sont normalisées
comme à l'affichage (aspect identique, /Rotate ramené à 0).
"""

from __future__ import annotations

import getpass
import logging
from pathlib import Path

from mesureplan import annotations as ann
from mesureplan import motifs
from mesureplan.annotations import Annotation, TypeAnnotation

journal = logging.getLogger(__name__)

MODE_INCRUSTE = "incrusté"
MODE_ANNOTATIONS = "annotations"


def exporter(source: Path, sortie: Path, par_page: dict[int, list[Annotation]], mode: str) -> dict[str, int]:
    """Écrit la copie annotée ; retourne des compteurs {incrustées, annotations, échecs}."""
    if Path(source).resolve() == Path(sortie).resolve():
        raise ValueError("Le fichier de sortie doit être différent du plan d'origine.")
    doc, compteurs = document_annote(source, par_page, mode)
    try:
        doc.save(sortie, garbage=3, deflate=True)
    finally:
        doc.close()
    journal.info("Export PDF %s (%s) : %s", sortie, mode, compteurs)
    return compteurs


def document_annote(source: Path, par_page: dict[int, list[Annotation]], mode: str):
    """Ouvre une copie en mémoire du PDF et y ajoute les éléments ; retourne (document, compteurs).

    L'appelant est responsable de la fermeture du document retourné.
    """
    import pymupdf

    compteurs = {"incrustées": 0, "annotations": 0, "échecs": 0}
    doc = pymupdf.open(source)
    try:
        for page in doc:
            if page.rotation:
                page.remove_rotation()  # même repère que celui des coordonnées enregistrées
        try:
            auteur = getpass.getuser()
        except Exception:  # noqa: BLE001
            auteur = "MesurePlan"
        for numero, elements in sorted(par_page.items()):
            if not 0 <= numero < doc.page_count:
                continue
            page = doc[numero]
            for element in elements:
                try:
                    if mode == MODE_ANNOTATIONS:
                        try:
                            _annoter(pymupdf, page, element, auteur)
                            compteurs["annotations"] += 1
                            continue
                        except Exception:
                            journal.exception("Annotation PDF impossible (%s) : incrustation à la place",
                                              element.type.value)
                    _incruster(pymupdf, page, element)
                    compteurs["incrustées"] += 1
                except Exception:
                    journal.exception("Élément non exporté : %s page %d", element.type.value, numero + 1)
                    compteurs["échecs"] += 1
    except Exception:
        doc.close()
        raise
    return doc, compteurs


# ---------------------------------------------------------------------------
# Mode incrusté
# ---------------------------------------------------------------------------

def _tirets_pdf(style: ann.Style) -> str | None:
    motif = ann.motif_tirets(style.trait, style.epaisseur)
    return None if motif is None else "[" + " ".join(f"{v:.2f}" for v in motif) + "] 0"


def _largeur_texte(pymupdf, texte: str, taille: float) -> float:
    return max(pymupdf.get_text_length(ligne, fontname="helv", fontsize=taille) for ligne in texte.split("\n"))


def _incruster(pymupdf, page, a: Annotation) -> None:
    st = a.style
    trait = ann.hex_vers_rgb(st.couleur_trait)
    fond = ann.hex_vers_rgb(st.couleur_fond) if st.couleur_fond and a.type in ann.TYPES_REMPLISSABLES else None
    opacite = st.opacite_fond if fond else 1.0
    tirets = _tirets_pdf(st)
    arrondi = 1 if st.trait == "pointillés" else 0
    P = pymupdf.Point  # noqa: N806

    if a.type is TypeAnnotation.TEXTE:
        _incruster_texte(pymupdf, page, a, trait, fond, opacite)
        return

    if st.motif and a.type in ann.TYPES_MOTIF:
        # Ordre de superposition identique à l'écran : fond, puis motif, puis contour
        if fond is not None:
            fond_seul = page.new_shape()
            fond_seul.draw_polyline([P(*q) for q in a.contour() + [a.contour()[0]]])
            fond_seul.finish(color=None, fill=fond, fill_opacity=opacite, closePath=True)
            fond_seul.commit()
            fond = None
        incruster_motif(pymupdf, page, a)

    forme = page.new_shape()
    ferme = False
    if a.type is TypeAnnotation.LIGNE:
        forme.draw_line(P(*a.points[0]), P(*a.points[1]))
    elif a.type is TypeAnnotation.FLECHE:
        queue, tete = a.points[0], a.points[1]
        longueur = ann.longueur_pointe(st.epaisseur)
        debut = ann.recul_pointe(tete, queue, longueur) if st.double_fleche else queue
        forme.draw_line(P(*debut), P(*ann.recul_pointe(queue, tete, longueur)))
    elif a.type is TypeAnnotation.POLYLIGNE:
        forme.draw_polyline([P(*p) for p in a.points])
    elif a.type is TypeAnnotation.POLYGONE:
        forme.draw_polyline([P(*p) for p in a.points + [a.points[0]]])
        ferme = True
    elif a.type is TypeAnnotation.RECTANGLE:
        # Les quatre coins tiennent compte de la rotation
        forme.draw_polyline([P(*q) for q in a.coins() + [a.coins()[0]]])
        ferme = True
    elif a.type is TypeAnnotation.ELLIPSE:
        if a.tournee:
            forme.draw_polyline([P(*q) for q in a.contour() + [a.contour()[0]]])
        else:
            forme.draw_oval(pymupdf.Rect(*a.boite()))
        ferme = True
    elif a.type is TypeAnnotation.CERCLE:
        forme.draw_circle(P(*a.points[0]), a.rayon)
        ferme = True
    forme.finish(color=trait, fill=fond, width=st.epaisseur, dashes=tirets, closePath=ferme,
                 fill_opacity=opacite, lineCap=arrondi, lineJoin=1)

    if a.type is TypeAnnotation.FLECHE:
        # Pointe(s) pleine(s), toujours en trait plein
        longueur = ann.longueur_pointe(st.epaisseur)
        pointes = [ann.pointe_fleche(a.points[0], a.points[1], longueur)]
        if st.double_fleche:
            pointes.append(ann.pointe_fleche(a.points[1], a.points[0], longueur))
        for triangle in pointes:
            forme.draw_polyline([P(*p) for p in triangle + [triangle[0]]])
            forme.finish(color=trait, fill=trait, width=0.5, closePath=True, lineJoin=1)
    forme.commit()


def incruster_motif(pymupdf, page, a: Annotation) -> int:
    """Dessine le motif de remplissage (déjà découpé par le contour) ; retourne le nombre de primitives."""
    st = a.style
    prim = motifs.generer(st.motif, a.contour(), st.motif_angle, st.motif_echelle)
    if not prim.taille:
        return 0
    couleur = ann.hex_vers_rgb(st.motif_couleur or st.couleur_trait)
    largeur = max(st.motif_epaisseur, 0.05)
    P = pymupdf.Point  # noqa: N806
    if prim.segments:
        forme = page.new_shape()
        for p, q in prim.segments:
            forme.draw_line(P(*p), P(*q))
        forme.finish(color=couleur, width=largeur, lineCap=1, closePath=False)
        forme.commit()
    if prim.cercles:
        forme = page.new_shape()
        for c, r in prim.cercles:
            forme.draw_circle(P(*c), r)
        forme.finish(color=couleur, width=largeur)
        forme.commit()
    if prim.points:
        forme = page.new_shape()
        for c, r in prim.points:
            forme.draw_circle(P(*c), r)
        forme.finish(color=None, fill=couleur)
        forme.commit()
    if prim.densite_reduite:
        journal.warning("Motif « %s » : espacement augmenté pour limiter le volume du PDF", st.motif)
    return prim.taille


def _incruster_texte(pymupdf, page, a: Annotation, trait, fond, opacite: float) -> None:
    st = a.style
    texte = ann.texte_pdf(a.texte)
    taille = st.taille_police
    x0, y0, x1, y1 = a.boite(_largeur_texte(pymupdf, texte, taille))
    if fond is not None or st.cadre_texte:
        forme = page.new_shape()
        forme.draw_rect(pymupdf.Rect(x0, y0, x1, y1))
        forme.finish(color=trait if st.cadre_texte else None, fill=fond, width=max(0.4, st.epaisseur * 0.5),
                     fill_opacity=opacite)
        forme.commit()
    marge = ann.MARGE_TEXTE * taille
    for i, ligne in enumerate(texte.split("\n")):
        base = y0 + marge + taille * (ann.LIGNE_DE_BASE + i * ann.INTERLIGNE)
        page.insert_text(pymupdf.Point(x0 + marge, base), ligne, fontsize=taille, fontname="helv", color=trait)


# ---------------------------------------------------------------------------
# Mode annotations PDF
# ---------------------------------------------------------------------------

def _annoter(pymupdf, page, a: Annotation, auteur: str) -> None:
    st = a.style
    trait = ann.hex_vers_rgb(st.couleur_trait)
    fond = ann.hex_vers_rgb(st.couleur_fond) if st.couleur_fond and a.type in ann.TYPES_REMPLISSABLES else None
    P = pymupdf.Point  # noqa: N806

    if a.type is TypeAnnotation.TEXTE:
        texte = ann.texte_pdf(a.texte)
        rect = pymupdf.Rect(*a.boite(_largeur_texte(pymupdf, texte, st.taille_police)))
        # Légère réserve : les visionneuses ajoutent leur propre marge intérieure
        rect.x1 += st.taille_police
        rect.y1 += st.taille_police * 0.3
        annot = page.add_freetext_annot(rect, texte, fontsize=st.taille_police, fontname="helv",
                                        text_color=trait, fill_color=fond)
        annot.set_border(width=max(0.4, st.epaisseur * 0.5) if st.cadre_texte else 0)
    else:
        if a.type is TypeAnnotation.LIGNE or a.type is TypeAnnotation.FLECHE:
            annot = page.add_line_annot(P(*a.points[0]), P(*a.points[1]))
            if a.type is TypeAnnotation.FLECHE:
                pointe = pymupdf.PDF_ANNOT_LE_CLOSED_ARROW
                annot.set_line_ends(pointe if st.double_fleche else pymupdf.PDF_ANNOT_LE_NONE, pointe)
                fond = trait  # remplissage des pointes
        elif a.type is TypeAnnotation.POLYLIGNE:
            annot = page.add_polyline_annot([P(*p) for p in a.points])
        elif a.type is TypeAnnotation.POLYGONE:
            annot = page.add_polygon_annot([P(*p) for p in a.points])
        elif a.tournee:
            # Rectangle / ovale tourné : pas d'équivalent natif, polygone de même contour
            annot = page.add_polygon_annot([P(*q) for q in a.contour()])
        elif a.type is TypeAnnotation.RECTANGLE:
            annot = page.add_rect_annot(pymupdf.Rect(*a.boite()))
        else:  # ellipse, cercle
            annot = page.add_circle_annot(pymupdf.Rect(*a.boite()))
        if st.motif and a.type in ann.TYPES_MOTIF:
            # Les annotations PDF ne savent pas hachurer : motif incrusté sous l'annotation
            incruster_motif(pymupdf, page, a)
        annot.set_colors(stroke=trait, fill=fond)
        motif = ann.motif_tirets(st.trait, st.epaisseur)
        # Les bordures d'annotation n'acceptent que des tirets entiers (pt)
        annot.set_border(width=st.epaisseur, dashes=[max(1, round(v)) for v in motif] if motif else None)
        # Une annotation n'a qu'une opacité globale : appliquée seulement si la forme a un fond
        if st.couleur_fond and a.type in ann.TYPES_REMPLISSABLES and st.opacite_fond < 1:
            annot.set_opacity(max(st.opacite_fond, 0.2))
    annot.set_info(title=auteur, content=a.texte or a.type.value, subject="MesurePlan")
    annot.update()

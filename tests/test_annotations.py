"""Tests du modèle d'annotations (sans dépendance graphique)."""

from __future__ import annotations

import math

from mesureplan import annotations as ann
from mesureplan.annotations import Annotation, Style, TypeAnnotation
from mesureplan.echelle import EchellePage
from mesureplan.mesures import Formateur, Session, TypeMesure


def test_boites_et_cercle():
    c = Annotation(1, TypeAnnotation.CERCLE, 0, [(50, 50), (53, 54)])
    assert c.rayon == 5 and c.boite() == (45, 45, 55, 55)
    r = Annotation(2, TypeAnnotation.RECTANGLE, 0, [(10, 20), (0, 0)])
    assert r.boite() == (0, 0, 10, 20)


def test_distance_selon_remplissage():
    vide = Annotation(1, TypeAnnotation.RECTANGLE, 0, [(0, 0), (100, 50)])
    assert math.isclose(vide.distance((50, 25)), 25)  # au centre : loin des bords
    plein = Annotation(2, TypeAnnotation.RECTANGLE, 0, [(0, 0), (100, 50)], Style(couleur_fond="#FFFF00"))
    assert plein.distance((50, 25)) == 0
    ellipse = Annotation(3, TypeAnnotation.ELLIPSE, 0, [(0, 0), (100, 50)])
    assert ellipse.distance((100, 25)) < 1e-9 and ellipse.distance((50, 25)) > 20
    fleche = Annotation(4, TypeAnnotation.FLECHE, 0, [(0, 0), (100, 0)])
    assert math.isclose(fleche.distance((50, 3)), 3)
    poly = Annotation(5, TypeAnnotation.POLYGONE, 0, [(0, 0), (10, 0), (10, 10)], Style(couleur_fond="#00FF00"))
    assert poly.distance((8, 2)) == 0 and poly.distance((2, 8)) > 0


def test_texte_boite_et_centre():
    t = Annotation(1, TypeAnnotation.TEXTE, 0, [(100, 100)], Style(taille_police=10), "abc\nde")
    x0, y0, x1, y1 = t.boite(largeur_texte=20)
    assert (x0, y0) == (100, 100) and math.isclose(x1 - x0, 26) and math.isclose(y1 - y0, 31)
    t.centre = True
    x0, y0, x1, y1 = t.boite(largeur_texte=20)
    assert math.isclose((x0 + x1) / 2, 100) and math.isclose((y0 + y1) / 2, 100)
    assert t.distance((105, 100)) == 0


def test_pointe_de_fleche():
    tete, g, d = ann.pointe_fleche((0, 0), (100, 0), 10, 30)
    assert tete == (100, 0)
    assert math.isclose(g[0], 100 - 10 * math.cos(math.radians(30)))
    assert math.isclose(g[1], -d[1])  # ailes symétriques
    x, y = ann.recul_pointe((0, 0), (100, 0), 10)
    assert math.isclose(x, 92) and y == 0


def test_utilitaires_rendu():
    assert ann.hex_vers_rgb("#FF8000") == (1.0, 128 / 255, 0.0)
    assert ann.hex_vers_rgb("#fff") == (1.0, 1.0, 1.0)
    assert ann.motif_tirets("plein", 1) is None and ann.motif_tirets("tirets", 2) == [8, 5]
    assert ann.texte_pdf("Σ 1 234,50 m²  – ok") == "Tot. 1 234,50 m²  - ok"
    assert ann.texte_pdf("α") == "?"


def test_deplacement_et_persistance():
    s = Session("plan.pdf")
    m = s.ajouter_mesure(TypeMesure.DISTANCE, 0, [(0, 0), (10, 0)])
    a = s.ajouter_annotation(TypeAnnotation.FLECHE, 0, [(0, 0), (10, 10)],
                             Style(couleur_trait="#123456", double_fleche=True))
    assert a.identifiant != m.identifiant
    a.deplacer(5, -5)
    assert a.points == [(5, -5), (15, 5)]
    s2 = Session.depuis_dict(s.vers_dict())
    a2 = s2.annotation(a.identifiant)
    assert a2.style.couleur_trait == "#123456" and a2.style.double_fleche and a2.points == [(5, -5), (15, 5)]
    assert s2.supprimer_mesures({a.identifiant, m.identifiant}) == 2
    # Compatibilité : une session du format 1 (sans annotations) reste lisible
    ancien = s.vers_dict()
    ancien["format"] = 1
    del ancien["annotations"]
    assert Session.depuis_dict(ancien).annotations == []


def test_style_tolere_cles_inconnues():
    st = Style.depuis_dict({"couleur_trait": "#000000", "cle_future": 3})
    assert st.couleur_trait == "#000000"


def test_primitives_des_mesures():
    s = Session("plan.pdf")
    surf = s.ajouter_mesure(TypeMesure.SURFACE, 0, [(0, 0), (100, 0), (100, 100), (0, 100)])
    formes = ann.primitives_mesure(surf, EchellePage(100), Formateur(), "#E4572E")
    assert [f.type for f in formes] == [TypeAnnotation.POLYGONE, TypeAnnotation.TEXTE]
    assert formes[1].centre and formes[1].points[0] == (50, 50) and "m²" in formes[1].texte
    angle = s.ajouter_mesure(TypeMesure.ANGLE, 0, [(10, 0), (0, 0), (0, 10)])
    texte = ann.primitives_mesure(angle, EchellePage(100), Formateur(), "#E4572E")[1]
    assert texte.texte == "90,0°" and texte.points[0][0] > 0 and texte.points[0][1] > 0

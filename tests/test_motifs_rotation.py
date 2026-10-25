"""Tests de la rotation, des poignées d'édition et des motifs de remplissage."""

from __future__ import annotations

import math

from mesureplan import geometrie as geo
from mesureplan import motifs
from mesureplan.annotations import Annotation, Style, TypeAnnotation


def proche(p, q, tol=1e-9):
    return math.isclose(p[0], q[0], abs_tol=tol) and math.isclose(p[1], q[1], abs_tol=tol)


def test_rotation_sens_trigonometrique_ecran():
    # +90° : un point à droite du centre passe au-dessus (Y écran vers le bas)
    assert proche(geo.tourner((10, 0), (0, 0), 90), (0, -10))
    assert proche(geo.tourner(geo.tourner((3, 4), (1, 1), 37), (1, 1), -37), (3, 4))


def test_rectangle_tourne_contour_et_distance():
    r = Annotation(1, TypeAnnotation.RECTANGLE, 0, [(-20, -10), (20, 10)], Style(couleur_fond="#FFFFFF"))
    r.definir_orientation(90)
    assert math.isclose(r.orientation, 90)
    xs = [p[0] for p in r.contour()]
    ys = [p[1] for p in r.contour()]
    assert math.isclose(max(xs) - min(xs), 20) and math.isclose(max(ys) - min(ys), 40)
    assert r.distance((0, 15)) == 0       # à l'intérieur après rotation
    assert r.distance((15, 0)) > 4        # en dehors après rotation (était dedans avant)
    assert math.isclose(r.boite_englobante()[3] - r.boite_englobante()[1], 40)


def test_redimensionnement_coin_oppose_fixe():
    r = Annotation(1, TypeAnnotation.RECTANGLE, 0, [(0, 0), (40, 20)], angle=30)
    coins = r.coins()
    oppose = coins[2]
    nouveau = geo.tourner((80, 40), r.centre_geometrique(), 0)
    r.deplacer_poignee(0, nouveau)
    # Le coin tiré et le coin opposé sont bien deux coins de la nouvelle forme
    assert any(proche(c, nouveau, 1e-6) for c in r.coins()) and any(proche(c, oppose, 1e-6) for c in r.coins())
    assert math.isclose(r.angle, 30)


def test_orientation_des_lignes_et_fleches():
    f = Annotation(1, TypeAnnotation.FLECHE, 0, [(0, 0), (10, 0)])
    assert math.isclose(f.orientation, 0)
    f.definir_orientation(90)
    assert proche(f.points[0], (5, 5)) and proche(f.points[1], (5, -5))  # rotation autour du milieu
    assert math.isclose(geo.distance(*f.points), 10)
    assert Annotation(2, TypeAnnotation.POLYGONE, 0, [(0, 0), (1, 0), (0, 1)]).orientation is None


def test_poignees_par_type():
    assert len(Annotation(1, TypeAnnotation.ELLIPSE, 0, [(0, 0), (4, 2)]).poignees()) == 4
    assert Annotation(1, TypeAnnotation.TEXTE, 0, [(0, 0)], texte="a").poignees() == []
    c = Annotation(1, TypeAnnotation.CERCLE, 0, [(0, 0), (5, 0)])
    c.deplacer_poignee(0, (10, 10))  # centre : déplace tout le cercle
    assert c.points == [(10, 10), (15, 10)]
    c.deplacer_poignee(1, (10, 20))  # bord : change le rayon
    assert math.isclose(c.rayon, 10)


def test_persistance_angle_et_motif():
    st = Style(motif="beton", motif_angle=15, motif_echelle=2, motif_couleur="#333333")
    a = Annotation(1, TypeAnnotation.ELLIPSE, 0, [(0, 0), (10, 5)], st, angle=-25)
    b = Annotation.depuis_dict(a.vers_dict())
    assert b.angle == -25 and b.style.motif == "beton" and b.style.motif_echelle == 2


def test_decoupe_segment():
    carre = [(0, 0), (10, 0), (10, 10), (0, 10)]
    boite = (0, 0, 10, 10)
    assert motifs.decouper_segment((-5, 5), (15, 5), carre, boite) == [((0, 5), (10, 5))]
    assert motifs.decouper_segment((-5, 20), (15, 20), carre, boite) == []
    # Polygone en U : la traversée du creux donne deux morceaux
    u = [(0, 0), (10, 0), (10, 10), (7, 10), (7, 3), (3, 3), (3, 10), (0, 10)]
    morceaux = motifs.decouper_segment((-1, 6), (11, 6), u, (0, 0, 10, 10))
    assert [(round(a[0], 6), round(b[0], 6)) for a, b in morceaux] == [(0, 3), (7, 10)]


def test_tous_les_motifs_restent_dans_le_contour():
    cercle = Annotation(1, TypeAnnotation.CERCLE, 0, [(100, 100), (160, 100)]).contour()
    for code in motifs.MOTIFS:
        prim = motifs.generer(code, cercle, angle=20, echelle=1.0)
        assert prim.taille > 0, code
        for a, b in prim.segments:
            for p in (a, b, geo.milieu(a, b)):
                assert geo.distance(p, (100, 100)) <= 60 + 1e-6, code
        for c, _r in prim.points + prim.cercles:
            assert geo.distance(c, (100, 100)) <= 60, code


def test_motif_hachures_espacement_et_angle():
    carre = [(0, 0), (100, 0), (100, 100), (0, 100)]
    prim = motifs.generer("hachures", carre, angle=-45, echelle=2)  # 45 + (-45) = horizontal, pas 6 pt
    ys = sorted({round(a[1], 6) for a, b in prim.segments})
    assert all(math.isclose(a[1], b[1], abs_tol=1e-9) for a, b in prim.segments)
    ecarts = {round(y2 - y1, 6) for y1, y2 in zip(ys, ys[1:])}
    assert ecarts == {6.0}


def test_motif_deterministe_et_limite():
    carre = [(0, 0), (50, 0), (50, 50), (0, 50)]
    assert motifs.generer("beton", carre).segments == motifs.generer("beton", carre).segments
    immense = [(0, 0), (5000, 0), (5000, 5000), (0, 5000)]
    prim = motifs.generer("sable", immense, echelle=0.1)
    assert prim.densite_reduite and prim.taille < motifs.ELEMENTS_MAX * 2

"""Tests des calculs de l'extension (sans Inkscape). Lancement : pytest depuis le dossier de l'extension."""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mesureplan_calcul as calc  # noqa: E402


def droit(points):
    """Superchemin d'une polyligne : poignées confondues avec les nœuds."""
    return [[[list(p), list(p), list(p)] for p in points]]


def test_unites_document():
    # Import PDF A3 paysage typique : largeur en mm, viewBox en mm
    assert math.isclose(calc.mm_papier_par_uu("420mm", "0 0 420 297"), 1.0)
    # Document en points (1190,55 pt = 420 mm)
    assert math.isclose(calc.mm_papier_par_uu("1190.55pt", "0 0 1190.55 841.89"), 25.4 / 72)
    # Sans viewBox : 1 uu = 1 px CSS
    assert math.isclose(calc.mm_papier_par_uu("1587", None), 25.4 / 96)


def test_rectangle_ferme():
    sc = calc.aplatir(droit([(0, 0), (42, 0), (42, 35), (0, 35), (0, 0)]), [True])[0]
    assert sc.ferme and sc.rectiligne and len(sc.noeuds) == 4
    assert math.isclose(calc.aire(sc.polyligne), 42 * 35)
    assert math.isclose(calc.longueur(sc.polyligne, True), 154)


def test_courbe_quart_de_cercle():
    k = 0.5522847498 * 100  # approximation cubique standard d'un quart de cercle de rayon 100
    sur = [[[[100, 0], [100, 0], [100, k]], [[k, 100], [0, 100], [0, 100]]]]  # centre (0,0), de (100,0) à (0,100)
    sc = calc.aplatir(sur, [False])[0]
    assert not sc.rectiligne
    assert math.isclose(calc.longueur(sc.polyligne, False), math.pi * 50, rel_tol=1e-3)


def test_echelle_et_calibration():
    e = calc.EchelleDocument(mm_par_uu=1.0, denominateur=100)
    assert math.isclose(42 * e.facteur, 4.2)  # 42 mm papier au 1:100 = 4,20 m
    e.ajouter_reference(97.0, 10.0, remplacer=True)  # plan imprimé à 97 %
    assert math.isclose(e.denominateur_effectif, 100 / 0.97)
    assert math.isclose(e.ecart_pct, (1 / 0.97 - 1) * 100)
    e.ajouter_reference(77.6, 8.0, remplacer=False)
    assert e.dispersion_pct < 1e-9
    texte = e.vers_json()
    e2 = calc.EchelleDocument.depuis_json(texte, 1.0, 50)
    assert e2.denominateur == 100 and len(e2.references) == 2


def test_angles():
    assert math.isclose(calc.angle_sommet((10, 0), (0, 0), (0, 10)), 90)
    assert math.isclose(calc.angle_entre_droites((0, 0), (1, 0), (0, 0), (1, 1)), 45)
    assert math.isclose(calc.angle_entre_droites((0, 0), (1, 0), (5, 5), (4, 6)), 45)
    x, y = calc.intersection_droites((0, 0), (10, 0), (5, -5), (5, 5))
    assert math.isclose(x, 5) and math.isclose(y, 0)
    px, py = calc.point_bissectrice((10, 0), (0, 0), (0, 10), math.sqrt(2))
    assert math.isclose(px, 1) and math.isclose(py, 1)


def test_detection_et_format():
    assert calc.detecter_echelle("PLAN RDC Échelle : 1/100 Lot 1/3 le 12/03/2026") == 100
    assert calc.detecter_echelle("rien ici 1/3") is None
    f = calc.Formateur("m", 2)
    assert f.longueur(1234.5) == "1 234,50 m" and f.surface(14.7) == "14,70 m²"

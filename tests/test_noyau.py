"""Tests du noyau de calcul (aucune dépendance graphique ni PyMuPDF requise).

Lancement : pytest   (depuis la racine du projet)
"""

from __future__ import annotations

import math
from types import SimpleNamespace

from mesureplan import geometrie as geo
from mesureplan.echelle import (METRES_PAR_POINT, EchellePage, Reference, detecter_echelle,
                                lire_denominateur)
from mesureplan.mesures import Formateur, Session, TypeMesure, formater_nombre
from mesureplan.pdf_document import segments_depuis_dessins


def pt(metres: float, denominateur: float = 100.0) -> float:
    """Longueur papier en points correspondant à « metres » réels à l'échelle 1:denominateur."""
    return metres / (METRES_PAR_POINT * denominateur)


# --- Géométrie ---------------------------------------------------------------

def test_distance_et_polyligne():
    assert geo.distance((0, 0), (3, 4)) == 5
    assert geo.longueur_polyligne([(0, 0), (3, 0), (3, 4)]) == 7
    assert geo.longueur_polyligne([(0, 0), (3, 0), (3, 4)], fermee=True) == 12


def test_aire_et_centroide():
    carre = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert geo.aire_polygone(carre) == 100
    assert geo.aire_polygone(list(reversed(carre))) == 100  # sens indifférent
    cx, cy = geo.centroide_polygone(carre)
    assert math.isclose(cx, 5) and math.isclose(cy, 5)
    # Pièce en L : 6×4 moins 2×2 = 20
    en_l = [(0, 0), (6, 0), (6, 4), (2, 4), (2, 2), (0, 2)]
    assert math.isclose(geo.aire_polygone(en_l), 20)


def test_auto_intersection():
    assert not geo.polygone_auto_intersecte([(0, 0), (10, 0), (10, 10), (0, 10)])
    assert geo.polygone_auto_intersecte([(0, 0), (10, 10), (10, 0), (0, 10)])  # « nœud papillon »


def test_angles():
    assert math.isclose(geo.angle_trois_points((10, 0), (0, 0), (0, 10)), 90)
    assert math.isclose(geo.angle_trois_points((10, 0), (0, 0), (10, 10)), 45)
    assert math.isclose(geo.angle_trois_points((10, 0), (0, 0), (-10, 0)), 180)


def test_intersection_et_projection():
    assert geo.intersection_segments((0, 0), (10, 10), (0, 10), (10, 0)) == (5, 5)
    assert geo.intersection_segments((0, 0), (1, 0), (0, 1), (1, 1)) is None
    projete, t = geo.projection_sur_segment((5, 3), (0, 0), (10, 0))
    assert projete == (5, 0) and t == 0.5


def test_contrainte_angulaire():
    x, y = geo.contraindre_angle((0, 0), (100, 7), 45)
    assert math.isclose(y, 0, abs_tol=1e-9) and math.isclose(x, 100)  # projection sur l'horizontale
    x, y = geo.contraindre_angle((0, 0), (50, 52), 45)
    assert math.isclose(x, y)


# --- Accrochage ----------------------------------------------------------------

def _index_carre():
    a, b, c, d = (0, 0), (100, 0), (100, 100), (0, 100)
    segs = [(a, b, geo.SEGMENT_COMPLET), (b, c, geo.SEGMENT_COMPLET),
            (c, d, geo.SEGMENT_COMPLET), (d, a, geo.SEGMENT_COMPLET),
            ((0, 0), (100, 100), geo.SEGMENT_COMPLET), ((0, 100), (100, 0), geo.SEGMENT_COMPLET),
            ((0, 30), (100, 30), geo.SEGMENT_COMPLET)]
    return geo.IndexSegments(segs, 10)


def test_accrochage_types():
    index = _index_carre()
    opts = geo.OptionsAccrochage()
    assert geo.accrocher((98, 101), index, 5, opts) == geo.Accrochage((100, 100), "extrémité")
    assert geo.accrocher((51, 2), index, 5, opts) == geo.Accrochage((50, 0), "milieu")
    assert geo.accrocher((31, 28), index, 5, opts) == geo.Accrochage((30, 30), "intersection")
    r = geo.accrocher((20, 2), index, 5, opts)
    assert r.type == "sur trait" and r.point == (20, 0)
    assert geo.accrocher((30, 60), index, 5, opts).type == "libre"
    assert geo.accrocher((60, 60), index, 1, opts, points_extra=[(60.5, 60)]).point == (60.5, 60)


def test_accrochage_desactive_par_type():
    index = _index_carre()
    opts = geo.OptionsAccrochage(extremites=False, milieux=False, intersections=False)
    assert geo.accrocher((98, 101), index, 5, opts).type == "sur trait"


# --- Extraction des traits PDF (format get_drawings simulé) ------------------------

def test_segments_depuis_dessins():
    rect = SimpleNamespace(x0=0, y0=0, x1=10, y1=20)
    dessins = [{"items": [("l", (0, 0), (5, 0)), ("re", rect, 1),
                          ("c", (0, 0), (0, 10), (10, 10), (10, 0)),
                          ("l", (1, 1), (1, 1.01))]}]  # le dernier est trop court : ignoré
    segs = segments_depuis_dessins(dessins)
    assert len(segs) == 1 + 4 + 8
    courbe = segs[5:]
    assert courbe[0][2] == geo.EXTREMITE_A and courbe[-1][2] == geo.EXTREMITE_B
    assert all(s[2] == 0 for s in courbe[1:-1])


# --- Échelle -----------------------------------------------------------------------

def test_echelle_cartouche():
    e = EchellePage(denominateur_cartouche=100)
    assert math.isclose(e.longueur_m(pt(5.0)), 5.0)
    assert math.isclose(e.surface_m2(pt(4.2) * pt(3.5)), 14.7)


def test_calibration_et_coherence():
    e = EchellePage(denominateur_cartouche=100)
    # Plan imprimé « ajusté à la page » à 99 % : la cote de 5,00 m mesure 4,95 m au cartouche
    e.references.append(Reference((0, 0), (pt(4.95), 0), 5.00))
    assert math.isclose(e.longueur_m(pt(4.95)), 5.00)
    assert math.isclose(e.ecart_cartouche_pct, (5.0 / 4.95 - 1) * 100)
    assert e.dispersion_pct is None
    e.references.append(Reference((0, 0), (0, pt(9.90)), 10.00))
    assert e.dispersion_pct < 1e-9  # deux références cohérentes
    e.references.append(Reference((0, 0), (0, pt(3.00)), 3.10))  # cote mal pointée
    assert e.dispersion_pct > 2


def test_saisie_echelle():
    assert lire_denominateur("1:100") == 100
    assert lire_denominateur("1/50") == 50
    assert lire_denominateur(" 200 ") == 200
    assert lire_denominateur("1:62,5") == 62.5


def test_detection_cartouche():
    texte = "PLAN DU RDC\nÉchelle : 1/100\nDate 12/03/2026\nDétail A 1/20\nIndice B 1/2"
    d = detecter_echelle(texte)
    assert d.denominateur == 100 and d.confirmee_par_mot_cle and 20 in d.autres
    assert detecter_echelle("Date 01/12/2025 – lot 1/3") is None
    assert detecter_echelle("COUPE AA 1:50").denominateur == 50


# --- Mesures, formatage, session ---------------------------------------------------

def test_mesures_recalculees_apres_calibration(tmp_path=None):
    s = Session("plan.pdf", denominateur_defaut=100)
    piece = [(0, 0), (pt(4.2), 0), (pt(4.2), pt(3.5)), (0, pt(3.5))]
    m = s.ajouter_mesure(TypeMesure.SURFACE, 0, piece)
    assert math.isclose(m.valeurs(s.echelle(0))["surface"], 14.7)
    assert math.isclose(m.valeurs(s.echelle(0))["perimetre"], 15.4)
    # Calibration : tout est recalculé sans retracer
    s.echelle(0).references.append(Reference((0, 0), (pt(4.2), 0), 4.41))  # +5 %
    assert math.isclose(m.valeurs(s.echelle(0))["surface"], 14.7 * 1.05 ** 2)


def test_formatage_francais():
    assert formater_nombre(1234.5, 2) == "1 234,50"
    f = Formateur(unite_longueur="cm")
    assert f.longueur(4.2) == "420,0 cm"
    assert f.angle(90) == "90,0°"


def test_session_aller_retour_et_csv(tmp_path=None):
    import tempfile
    from pathlib import Path

    dossier = Path(tmp_path or tempfile.mkdtemp())
    s = Session("plan.pdf")
    s.ajouter_mesure(TypeMesure.DISTANCE, 0, [(0, 0), (pt(5), 0)])
    s.ajouter_mesure(TypeMesure.ANGLE, 1, [(10, 0), (0, 0), (0, 10)])
    s.echelle(1).denominateur_cartouche = 50
    s.echelle(0).references.append(Reference((0, 0), (100, 0), 3.5))
    chemin = dossier / "plan.pdf.mesures.json"
    s.enregistrer(chemin)
    s2 = Session.charger(chemin)
    assert len(s2.mesures) == 2 and s2.echelle(1).denominateur_cartouche == 50
    assert s2.echelle(0).references[0].longueur_reelle_m == 3.5
    assert s2.ajouter_mesure(TypeMesure.DISTANCE, 0, [(0, 0), (1, 1)]).identifiant == 3
    n = s2.exporter_csv(dossier / "export.csv", Formateur())
    assert n == 3
    contenu = (dossier / "export.csv").read_text(encoding="utf-8-sig")
    assert "Longueur (m)" in contenu and "90,00" in contenu

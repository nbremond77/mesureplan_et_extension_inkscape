"""Tests du noyau de calcul 3D (sans Blender). Lancement : pytest depuis blender-mesureplan/."""

from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mesureplan_3d"))

import calcul3d as c  # noqa: E402


def proche(a, b, tol=1e-9):
    return all(math.isclose(x, y, abs_tol=tol) for x, y in zip(a, b))


def test_composantes_globales():
    v = c.composantes((0, 0, 0), (3, 4, 12))
    assert math.isclose(v["longueur"], 13) and (v["dx"], v["dy"], v["dz"]) == (3, 4, 12)
    assert math.isclose(v["horizontale"], 5)
    assert math.isclose(v["pente_deg"], math.degrees(math.atan2(12, 5)))
    assert math.isclose(v["pente_pct"], 240)
    assert math.isclose(v["angle_plan"], math.degrees(math.atan2(4, 3)))
    # Mesure verticale : pente 90°, pourcentage indéfini
    vert = c.composantes((1, 1, 0), (1, 1, 2.5))
    assert vert["pente_pct"] is None and math.isclose(vert["pente_deg"], 90)
    # Signes conservés dans l'autre sens
    inv = c.composantes((3, 4, 12), (0, 0, 0))
    assert (inv["dx"], inv["dy"], inv["dz"]) == (-3, -4, -12) and math.isclose(inv["pente_deg"], v["pente_deg"])


def test_composantes_repere_objet():
    # Repère d'un bâtiment tourné de 30° autour de Z : matrice monde → repère = Rz(-30°)
    a = math.radians(30)
    rot = ((math.cos(a), math.sin(a), 0), (-math.sin(a), math.cos(a), 0), (0, 0, 1))
    # Façade de 10 m le long de l'axe X du bâtiment
    b = (10 * math.cos(a), 10 * math.sin(a), 0)
    v = c.composantes((0, 0, 0), b, rot)
    assert math.isclose(v["dx"], 10) and math.isclose(v["dy"], 0, abs_tol=1e-9)
    chemin = c.points_decomposition((0, 0, 0), b, rot)
    assert proche(chemin[1], b) and proche(chemin[3], b)


def test_points_decomposition_global():
    assert c.points_decomposition((1, 2, 3), (4, 6, 15)) == [(1, 2, 3), (4, 2, 3), (4, 6, 3), (4, 6, 15)]


def test_surface_toit_incline():
    # Pan de toit 4 m (horizontal) × 3 m en projection, pente 30° : surface vraie = 12 / cos(30°)
    h = 3 * math.tan(math.radians(30))
    pan = [(0, 0, 0), (4, 0, 0), (4, 3, h), (0, 3, h)]
    s = c.surface(pan)
    assert math.isclose(s["surface"], 12 / math.cos(math.radians(30)))
    assert math.isclose(s["surface_xy"], 12) and math.isclose(s["pente_deg"], 30)
    assert s["planeite"] < 1e-9
    # Mur vertical : surface projetée nulle, pente 90°
    mur = [(0, 0, 0), (5, 0, 0), (5, 0, 2.5), (0, 0, 2.5)]
    assert math.isclose(c.surface(mur)["surface"], 12.5) and math.isclose(c.surface(mur)["pente_deg"], 90)
    assert c.surface(mur)["surface_xy"] < 1e-9


def test_surface_non_plane_detectee():
    gauche = [(0, 0, 0), (1, 0, 0), (1, 1, 0.2), (0, 1, 0)]
    assert c.surface(gauche)["planeite"] > 0.04


def test_chaine_et_angle():
    v = c.valeurs(c.CHAINE, [(0, 0, 0), (3, 0, 0), (3, 4, 1)])
    assert math.isclose(v["longueur"], 3 + math.sqrt(17)) and math.isclose(v["horizontale"], 7)
    assert v["dz"] == 1
    assert math.isclose(c.valeurs(c.ANGLE, [(1, 0, 0), (0, 0, 0), (0, 0, 1)])["angle"], 90)


def test_mise_a_l_echelle():
    assert c.mettre_a_l_echelle([(2, 0, 0), (0, 2, 4)], (0, 0, 0), 0.5) == [(1, 0, 0), (0, 1, 2)]


def test_accrochage_priorites():
    k = c.Candidat
    candidats = [k((100, 100), (0, 0, 0), "face"), k((105, 100), (1, 0, 0), "arête"),
                 k((108, 100), (2, 0, 0), "milieu"), k((108.4, 100), (3, 0, 0), "sommet")]
    # Un point remarquable dans la tolérance l'emporte sur l'arête plus proche ; sommet ≈ milieu → sommet
    assert c.choisir_accrochage((100, 100), candidats, 10).nature == "sommet"
    # Hors tolérance des points : arête
    assert c.choisir_accrochage((100, 100), candidats[:2], 10).nature == "arête"
    # Rien de ponctuel : face
    assert c.choisir_accrochage((100, 100), candidats[:1], 10).nature == "face"
    assert c.choisir_accrochage((100, 100), [], 10) is None


def test_pointilles():
    seg = c.segments_pointilles((0, 0), (20, 0), 6, 4)
    assert seg == [(0, 0), (6, 0), (10, 0), (16, 0)]
    assert len(seg) % 2 == 0 and c.segments_pointilles((1, 1), (1, 1)) == []


def test_etiquettes_et_detail():
    f = c.Formateur()
    v = c.valeurs(c.DISTANCE_XYZ, [(0, 0, 0), (4, -3, 1.2)])
    e = c.etiquettes(c.DISTANCE_XYZ, v, f)
    assert e.principale.startswith("L 5,14 m") and e.composantes == ("ΔX 4,00 m", "ΔY 3,00 m", "ΔZ 1,20 m")
    d = c.detail(c.DISTANCE_XYZ, v, f)
    assert "ΔY : -3,00 m" in d and "ΔZ : +1,20 m" in d and any(l.startswith("Pente : 13,5°") for l in d)
    surf = c.valeurs(c.SURFACE, [(0, 0, 0), (1, 0, 0), (1, 1, 0.2), (0, 1, 0)])
    assert any(l.startswith("⚠ Non plane") for l in c.detail(c.SURFACE, surf, f))
    assert c.etiquettes(c.ANGLE, {"angle": 90}, f, nom="Rampe").principale == "Rampe\n90,0°"


def test_export_csv():
    dossier = Path(tempfile.mkdtemp())
    v = c.valeurs(c.DISTANCE_XYZ, [(0, 0, 0), (3, 4, -12)])
    n = c.exporter_csv(dossier / "m.csv", [("Rampe", c.DISTANCE_XYZ, v, [(0, 0, 0), (3, 4, -12)])], "Global")
    assert n == 1
    entete, ligne = (dossier / "m.csv").read_text(encoding="utf-8-sig").splitlines()
    cols = dict(zip(entete.split(";"), ligne.split(";")))
    assert cols["Longueur (m)"] == "13,0000" and cols["ΔZ (m)"] == "-12,0000" and cols["Pente (%)"] == "240,00"
    assert cols["Type"] == "Distance XYZ" and cols["Repère"] == "Global"

"""Tests de la mise en page d'impression à l'échelle."""

from __future__ import annotations

import math

from mesureplan.echelle import METRES_PAR_POINT, EchellePage, Reference
from mesureplan.impression import (FORMATS_PAPIER, PT_PAR_MM, barre_echelle, facteur_agrandissement, nom_tuile,
                                   planifier)


def pt(metres: float, denominateur: float = 100.0) -> float:
    return metres / (METRES_PAR_POINT * denominateur)


def test_facteur_agrandissement():
    # Plan au 1:100 réimprimé au 1:50 : agrandissement ×2
    assert math.isclose(facteur_agrandissement(METRES_PAR_POINT * 100, 50), 2.0)
    # Plan imprimé à 97 % puis calibré : l'impression au 1:100 corrige l'écart (×1/0,97)
    e = EchellePage(100)
    e.references.append(Reference((0, 0), (pt(9.70), 0), 10.0))
    assert math.isclose(facteur_agrandissement(e.facteur, 100), 1 / 0.97)


def test_une_feuille_centree_et_dimension_exacte():
    # Maison 10 × 8 m au 1:100 → 100 × 80 mm : tient sur un A4
    zone = (50, 50, 50 + pt(10), 50 + pt(8))
    plan = planifier(zone, 1.0, FORMATS_PAPIER["A4"], "A4", denominateur=100)
    assert plan.nombre_feuilles == 1
    l_mm, h_mm = plan.taille_imprimee_mm
    assert math.isclose(l_mm, 100, rel_tol=1e-9) and math.isclose(h_mm, 80, rel_tol=1e-9)
    t = plan.tuiles[0]
    assert t.source == zone
    x0, y0, x1, y1 = t.destination
    ux0, uy0, ux1, uy1 = plan.zone_utile
    assert math.isclose((x0 + x1) / 2, (ux0 + ux1) / 2) and math.isclose((y0 + y1) / 2, (uy0 + uy1) / 2)


def test_orientation_automatique():
    # Zone très large : le paysage évite une 2e feuille
    zone = (0, 0, 250 * PT_PAR_MM, 100 * PT_PAR_MM)
    plan = planifier(zone, 1.0, FORMATS_PAPIER["A4"], "A4")
    assert plan.orientation == "paysage" and plan.nombre_feuilles == 1
    plan_portrait = planifier(zone, 1.0, FORMATS_PAPIER["A4"], "A4", orientation="portrait")
    assert plan_portrait.nombre_feuilles == 2


def test_mosaique_avec_recouvrement_couvre_toute_la_zone():
    # Plan A1 (841 × 594 mm) à imprimer sur A4 avec 10 mm de recouvrement
    zone = (0, 0, 841 * PT_PAR_MM, 594 * PT_PAR_MM)
    plan = planifier(zone, 1.0, FORMATS_PAPIER["A4"], "A4", recouvrement_mm=10)
    assert plan.nombre_feuilles == plan.lignes * plan.colonnes == len(plan.tuiles) > 1
    ux0, uy0, ux1, uy1 = plan.zone_utile
    for t in plan.tuiles:
        # Échelle conservée : taille source × k = taille destination
        sx = (t.source[2] - t.source[0]) * plan.k
        dx = t.destination[2] - t.destination[0]
        assert math.isclose(sx, dx) and dx <= ux1 - ux0 + 1e-6
        assert t.destination[3] - t.destination[1] <= uy1 - uy0 + 1e-6
    # Recouvrement entre deux colonnes voisines, et dernière colonne qui atteint le bord de la zone
    ligne0 = sorted((t for t in plan.tuiles if t.ligne == 0), key=lambda t: t.colonne)
    assert math.isclose(ligne0[0].source[2] - ligne0[1].source[0], 10 * PT_PAR_MM)
    assert math.isclose(ligne0[-1].source[2], zone[2])
    assert math.isclose(max(t.source[3] for t in plan.tuiles), zone[3])


def test_barre_echelle_et_noms():
    assert barre_echelle(100) == (5, 5, 50.0)
    longueur, divisions, mm = barre_echelle(50)
    assert longueur == 2 and divisions == 4 and mm == 40
    assert barre_echelle(500)[0] == 20
    from mesureplan.impression import Tuile
    assert nom_tuile(Tuile(0, 0, (0, 0, 1, 1), (0, 0, 1, 1))) == "A1"
    assert nom_tuile(Tuile(2, 3, (0, 0, 1, 1), (0, 0, 1, 1))) == "C4"
    assert nom_tuile(Tuile(26, 0, (0, 0, 1, 1), (0, 0, 1, 1))) == "AA1"

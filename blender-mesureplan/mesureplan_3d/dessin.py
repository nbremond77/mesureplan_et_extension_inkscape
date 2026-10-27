"""Dessin des mesures dans la vue 3D (module gpu + blf).

Un seul gestionnaire de dessin, en espace écran (POST_PIXEL), affiche :
  - les mesures enregistrées de la scène (traits, points, étiquettes) ;
  - le tracé en cours de l'outil modal (aperçu, marqueur d'accrochage, valeur en direct).
Tout est dessiné en pixels après projection : les mesures restent visibles à
travers les objets, et les pointillés gardent une taille constante à l'écran.
Un segment dont une extrémité est derrière la caméra n'est pas dessiné.
"""

from __future__ import annotations

import logging

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from . import calcul3d as c
from . import proprietes, socle
from .accrochage import ecran

journal = logging.getLogger(socle.NOM_JOURNAL)

# État du tracé en cours, renseigné par l'opérateur modal (None hors tracé)
ETAT_OUTIL: dict | None = None

_gestionnaire = None
_erreur_signalee = False


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

def _shader_trait():
    return gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")


def _shader_plein():
    return gpu.shader.from_builtin("UNIFORM_COLOR")


def traits(points_2d: list, couleur, largeur: float) -> None:
    """Segments indépendants : points_2d = [a1, b1, a2, b2, …]."""
    if len(points_2d) < 2:
        return
    shader = _shader_trait()
    lot = batch_for_shader(shader, "LINES", {"pos": [(x, y, 0.0) for x, y in points_2d]})
    shader.bind()
    region = bpy.context.region
    shader.uniform_float("viewportSize", (region.width, region.height))
    shader.uniform_float("lineWidth", largeur)
    shader.uniform_float("color", couleur)
    lot.draw(shader)


def polyligne(points_2d: list, couleur, largeur: float, fermee: bool = False) -> None:
    """Polyligne : les segments dont une extrémité est hors champ (None) sont ignorés."""
    paires = []
    n = len(points_2d)
    for i in range(n - 1 + (1 if fermee and n > 2 else 0)):
        a, b = points_2d[i], points_2d[(i + 1) % n]
        if a is not None and b is not None:
            paires += [a, b]
    traits(paires, couleur, largeur)


def pointilles(a, b, couleur, largeur: float) -> None:
    if a is not None and b is not None:
        traits(c.segments_pointilles(a, b, 7.0, 4.0), couleur, largeur)


def rectangle(x0: float, y0: float, x1: float, y1: float, couleur) -> None:
    shader = _shader_plein()
    sommets = [(x0, y0, 0.0), (x1, y0, 0.0), (x1, y1, 0.0), (x0, y1, 0.0)]
    lot = batch_for_shader(shader, "TRIS", {"pos": sommets}, indices=((0, 1, 2), (0, 2, 3)))
    shader.bind()
    shader.uniform_float("color", couleur)
    lot.draw(shader)


def carre(p, demi: float, couleur, largeur: float = 1.5) -> None:
    """Petit carré creux (sommet de mesure, marqueur d'accrochage)."""
    if p is None:
        return
    x, y = p
    coins = [(x - demi, y - demi), (x + demi, y - demi), (x + demi, y + demi), (x - demi, y + demi)]
    polyligne(coins, couleur, largeur, fermee=True)


def etiquette(position, texte: str, couleur_texte, fond, taille: float, decalage=(0.0, 0.0)) -> None:
    """Texte multiligne centré sur la position (ou décalé), sur un fond semi-transparent."""
    if position is None or not texte:
        return
    police = 0
    blf.size(police, taille)
    lignes = texte.split("\n")
    hauteur_ligne = taille * 1.35
    largeur = max(blf.dimensions(police, ligne)[0] for ligne in lignes)
    marge = taille * 0.4
    l_totale, h_totale = largeur + 2 * marge, hauteur_ligne * len(lignes) + marge
    x0 = position[0] - l_totale / 2 + decalage[0] if not decalage[0] else position[0] + decalage[0]
    y_haut = position[1] + h_totale / 2 + decalage[1] if not decalage[1] else position[1] + decalage[1]
    rectangle(x0, y_haut - h_totale, x0 + l_totale, y_haut, fond)
    blf.color(police, *couleur_texte)
    for i, ligne in enumerate(lignes):
        blf.position(police, x0 + marge, y_haut - marge * 0.5 - (i + 1) * hauteur_ligne + taille * 0.35, 0)
        blf.draw(police, ligne)


# ---------------------------------------------------------------------------
# Une mesure
# ---------------------------------------------------------------------------

def _position_etiquette(type_mesure: str, pts3d: list, pts2d: list):
    """Point d'ancrage de l'étiquette principale."""
    if type_mesure == c.SURFACE:
        return ecran(bpy.context.region, bpy.context.region_data, c.centroide(pts3d))
    if type_mesure == c.ANGLE and len(pts2d) == 3 and None not in pts2d:
        (ax, ay), (sx, sy), (bx, by) = pts2d
        # Décalée depuis le sommet, du côté de la bissectrice des bras projetés
        ux, uy, vx, vy = ax - sx, ay - sy, bx - sx, by - sy
        nu, nv = max((ux * ux + uy * uy) ** 0.5, 1e-9), max((vx * vx + vy * vy) ** 0.5, 1e-9)
        dx, dy = ux / nu + vx / nv, uy / nu + vy / nv
        nd = max((dx * dx + dy * dy) ** 0.5, 1e-9)
        return (sx + dx / nd * 40, sy + dy / nd * 40)
    if type_mesure == c.CHAINE and len(pts3d) > 2:
        k = (len(pts3d) - 1) // 2
        return ecran(bpy.context.region, bpy.context.region_data, c.milieu(pts3d[k], pts3d[k + 1]))
    return ecran(bpy.context.region, bpy.context.region_data, c.milieu(pts3d[0], pts3d[-1]))


def dessiner_mesure(scene, cfg: dict, type_mesure: str, pts3d: list, couleur, nom: str = "",
                    apercu: bool = False) -> None:
    """Traits, sommets, composantes et étiquettes d'une mesure (enregistrée ou en cours)."""
    aff = cfg.get("affichage", {})
    region, rv3d = bpy.context.region, bpy.context.region_data
    echelle_ui = bpy.context.preferences.system.ui_scale
    epaisseur = float(aff.get("epaisseur_trait", 2.0)) * echelle_ui
    taille = float(aff.get("taille_police", 13)) * echelle_ui
    fond = aff.get("fond_etiquettes", (0.1, 0.11, 0.13, 0.8))
    pts2d = [ecran(region, rv3d, p) for p in pts3d]

    polyligne(pts2d, couleur, epaisseur, fermee=(type_mesure == c.SURFACE and len(pts3d) > 2))
    for p in pts2d:
        carre(p, 3.0 * echelle_ui, couleur, 1.2 * echelle_ui)
    if len(pts3d) < 2:
        return
    # Surface ou angle encore incomplets (aperçu) : on affiche la distance du segment en cours
    if type_mesure in (c.SURFACE, c.ANGLE) and len(pts3d) < 3:
        type_affiche = c.DISTANCE
        pts_valeur = pts3d[-2:]
    else:
        type_affiche = c.DISTANCE if type_mesure == c.CALIBRATION else type_mesure
        pts_valeur = pts3d
    v = proprietes.valeurs_points(scene, type_affiche, pts_valeur)
    fmt = proprietes.formateur(scene, cfg)
    textes = c.etiquettes(type_affiche, v, fmt, nom)

    # Composantes ΔX (rouge), ΔY (vert), ΔZ (bleu), à la manière des axes de Blender
    if type_affiche == c.DISTANCE_XYZ and proprietes.reglages(scene).afficher_composantes:
        chemin = c.points_decomposition(pts3d[0], pts3d[-1], proprietes.rotation_repere(scene))
        chemin2d = [ecran(region, rv3d, p) for p in chemin]
        couleurs = (aff.get("couleur_x"), aff.get("couleur_y"), aff.get("couleur_z"))
        for i in range(3):
            if c.distance(chemin[i], chemin[i + 1]) < 1e-9:
                continue  # composante nulle : rien à dessiner
            pointilles(chemin2d[i], chemin2d[i + 1], couleurs[i], 1.5 * echelle_ui)
            m = ecran(region, rv3d, c.milieu(chemin[i], chemin[i + 1]))
            etiquette(m, textes.composantes[i], couleurs[i], fond, taille * 0.85)

    if apercu:
        # Valeur en direct : décalée en bas à droite du curseur
        curseur = pts2d[-1]
        etiquette(curseur, textes.principale, couleur, fond, taille, decalage=(18.0, -14.0))
    else:
        etiquette(_position_etiquette(type_affiche, pts3d, pts2d), textes.principale, (1, 1, 1, 1), fond, taille)


# ---------------------------------------------------------------------------
# Gestionnaire de dessin
# ---------------------------------------------------------------------------

COULEURS_ACCROCHAGE = {"sommet": (0.0, 0.85, 0.35, 1.0), "mesure": (0.0, 0.85, 0.35, 1.0),
                       "milieu": (0.0, 0.65, 0.95, 1.0), "arête": (0.75, 0.40, 0.95, 1.0),
                       "face": (0.95, 0.60, 0.10, 1.0), "axe": (1.0, 1.0, 1.0, 1.0),
                       "libre": (0.6, 0.6, 0.6, 1.0)}


def _dessiner() -> None:
    """Appelé par Blender à chaque rafraîchissement de chaque vue 3D."""
    global _erreur_signalee
    contexte = bpy.context
    scene = contexte.scene
    if scene is None or not hasattr(scene, "mesureplan3d") or contexte.region_data is None:
        return
    try:
        cfg = socle.charger_configuration(__package__)
        aff = cfg.get("affichage", {})
        r = proprietes.reglages(scene)
        gpu.state.blend_set("ALPHA")
        if r.afficher:
            for i, mesure in enumerate(r.mesures):
                if not mesure.visible or len(mesure.points) < 2:
                    continue
                couleur = aff.get("couleur_selection") if i == r.index_actif else aff.get("couleur_mesures")
                dessiner_mesure(scene, cfg, mesure.type, proprietes.points_monde(mesure), couleur,
                                mesure.nom if mesure.nom_affiche else "")
        etat = ETAT_OUTIL
        if etat is not None and etat.get("courant") is not None:
            points = [tuple(p) for p in etat["points"]] + [tuple(etat["courant"])]
            couleur = aff.get("couleur_apercu", (0.85, 0.1, 0.4, 1.0))
            dessiner_mesure(scene, cfg, etat["type"], points, couleur, apercu=len(points) >= 2)
            # Marqueur d'accrochage (taille écran constante)
            p = ecran(contexte.region, contexte.region_data, etat["courant"])
            carre(p, 7.0 * contexte.preferences.system.ui_scale,
                  COULEURS_ACCROCHAGE.get(etat.get("nature", "libre"), (1, 1, 1, 1)), 2.0)
        _erreur_signalee = False
    except Exception:
        # Une exception dans un gestionnaire de dessin se répéterait à chaque image : journalisée une fois
        if not _erreur_signalee:
            journal.exception("Erreur pendant le dessin des mesures")
            _erreur_signalee = True
    finally:
        gpu.state.blend_set("NONE")


def activer() -> None:
    global _gestionnaire
    if _gestionnaire is None:
        _gestionnaire = bpy.types.SpaceView3D.draw_handler_add(_dessiner, (), "WINDOW", "POST_PIXEL")


def desactiver() -> None:
    global _gestionnaire, ETAT_OUTIL
    if _gestionnaire is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_gestionnaire, "WINDOW")
        _gestionnaire = None
    ETAT_OUTIL = None

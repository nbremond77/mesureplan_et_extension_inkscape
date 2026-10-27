"""Accrochage 3D : sommets, milieux d'arêtes, arêtes, faces, points des mesures, verrou d'axe.

Principe : un rayon est lancé depuis la souris dans la scène évaluée
(Scene.ray_cast). Le polygone touché fournit des candidats (ses sommets, les
milieux et les points les plus proches de ses arêtes, le point d'impact sur la
face) ; les points des mesures existantes s'y ajoutent. Le choix entre candidats
se fait en pixels par calcul3d.choisir_accrochage (règle identique à l'appli 2D).
"""

from __future__ import annotations

from mathutils import Vector, geometry
from bpy_extras import view3d_utils

from . import calcul3d as c
from . import proprietes


def rayon(region, rv3d, souris: tuple[float, float]) -> tuple[Vector, Vector]:
    """Origine et direction (unitaire) du rayon passant par le pixel « souris »."""
    origine = view3d_utils.region_2d_to_origin_3d(region, rv3d, souris)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, souris)
    return origine, direction.normalized()


def ecran(region, rv3d, p) -> tuple[float, float] | None:
    """Projection d'un point monde sur l'écran (None s'il est derrière la caméra)."""
    q = view3d_utils.location_3d_to_region_2d(region, rv3d, Vector(p))
    return None if q is None else (q.x, q.y)


def _point_arete(a: Vector, b: Vector, origine: Vector, direction: Vector) -> Vector | None:
    """Point de [a, b] le plus proche du rayon de la souris."""
    resultat = geometry.intersect_line_line(a, b, origine, origine + direction)
    if resultat is None:
        return None
    p = resultat[0]
    ab = b - a
    longueur2 = ab.length_squared
    if longueur2 < 1e-18:
        return a.copy()
    t = max(0.0, min(1.0, (p - a).dot(ab) / longueur2))
    return a + ab * t


def candidats_geometrie(context, region, rv3d, souris, options: dict) -> list[c.Candidat]:
    """Candidats issus du polygone sous la souris."""
    origine, direction = rayon(region, rv3d, souris)
    depsgraph = context.evaluated_depsgraph_get()
    touche, impact, _normale, indice, objet, matrice = context.scene.ray_cast(depsgraph, origine, direction)
    if not touche:
        return []
    candidats: list[c.Candidat] = []
    if options.get("faces", True):
        candidats.append(c.Candidat(ecran(region, rv3d, impact) or souris, tuple(impact), "face"))
    if objet is None or indice < 0:
        return candidats
    maillage = getattr(objet.evaluated_get(depsgraph), "data", None)
    polygones = getattr(maillage, "polygons", None)
    if polygones is None or indice >= len(polygones):
        return candidats
    sommets = [matrice @ maillage.vertices[i].co for i in polygones[indice].vertices]
    for i, a in enumerate(sommets):
        b = sommets[(i + 1) % len(sommets)]
        if options.get("sommets", True):
            q = ecran(region, rv3d, a)
            if q is not None:
                candidats.append(c.Candidat(q, tuple(a), "sommet"))
        if options.get("milieux", True):
            m = (a + b) / 2
            q = ecran(region, rv3d, m)
            if q is not None:
                candidats.append(c.Candidat(q, tuple(m), "milieu"))
        if options.get("aretes", True):
            p = _point_arete(a, b, origine, direction)
            q = ecran(region, rv3d, p) if p is not None else None
            if q is not None:
                candidats.append(c.Candidat(q, tuple(p), "arête"))
    return candidats


def candidats_mesures(scene, region, rv3d, en_cours: list) -> list[c.Candidat]:
    """Points des mesures visibles et du tracé en cours (pour enchaîner les mesures)."""
    candidats = []
    points = [p for m in proprietes.reglages(scene).mesures if m.visible for p in proprietes.points_monde(m)]
    for p in points + [tuple(p) for p in en_cours]:
        q = ecran(region, rv3d, p)
        if q is not None:
            candidats.append(c.Candidat(q, tuple(p), "mesure"))
    return candidats


def point_libre(region, rv3d, souris, precedent) -> Vector:
    """Point « dans le vide » : sur le sol (Z = 0) pour le premier point, sinon dans le plan
    perpendiculaire à la vue passant par le point précédent."""
    origine, direction = rayon(region, rv3d, souris)
    if precedent is None:
        p = geometry.intersect_line_plane(origine, origine + direction, Vector((0, 0, 0)), Vector((0, 0, 1)))
    else:
        p = geometry.intersect_line_plane(origine, origine + direction, Vector(precedent), direction)
    return p if p is not None else origine + direction * 10.0


def point_sur_axe(region, rv3d, souris, precedent, axe) -> Vector | None:
    """Point de l'axe (passant par le point précédent) le plus proche du rayon de la souris."""
    origine, direction = rayon(region, rv3d, souris)
    depart = Vector(precedent)
    resultat = geometry.intersect_line_line(depart, depart + Vector(axe), origine, origine + direction)
    return None if resultat is None else resultat[0]


def accrocher(context, region, rv3d, souris, cfg: dict, en_cours: list, sans_accrochage: bool,
              axe: tuple | None) -> tuple[Vector, str]:
    """Position retenue pour le prochain point et nature de l'accrochage."""
    precedent = en_cours[-1] if en_cours else None
    if axe is not None and precedent is not None:
        p = point_sur_axe(region, rv3d, souris, precedent, axe)
        if p is not None:
            return p, "axe"
    options = cfg.get("accrochage", {})
    tolerance = float(options.get("tolerance_pixels", 12)) * context.preferences.system.ui_scale
    candidats = candidats_geometrie(context, region, rv3d, souris, options)
    if sans_accrochage:
        # Ctrl : seulement le point touché sur la face, sinon point libre
        faces = [k for k in candidats if k.nature == "face"]
        return (Vector(faces[0].monde), "face") if faces else (point_libre(region, rv3d, souris, precedent), "libre")
    if options.get("points_des_mesures", True):
        candidats += candidats_mesures(context.scene, region, rv3d, en_cours)
    choisi = c.choisir_accrochage(souris, candidats, tolerance)
    if choisi is not None:
        return Vector(choisi.monde), choisi.nature
    return point_libre(region, rv3d, souris, precedent), "libre"

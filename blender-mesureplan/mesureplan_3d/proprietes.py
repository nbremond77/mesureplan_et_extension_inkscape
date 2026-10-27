"""Données de l'extension, enregistrées dans le fichier .blend (propriétés de scène).

Les points des mesures sont stockés en coordonnées MONDE (unités Blender) : les
valeurs réelles sont recalculées à chaque affichage avec l'échelle de la scène,
le facteur de calibration et le repère choisi. Changer l'un de ces réglages met
donc à jour toutes les mesures sans les retracer.
"""

# Pas de « from __future__ import annotations » : Blender lit les annotations de propriétés
# (bpy.props) comme des objets ; converties en chaînes, elles ne seraient pas enregistrées.

import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty, FloatVectorProperty,
                       IntProperty, PointerProperty, StringProperty)
from bpy.types import PropertyGroup

from . import calcul3d as c

TYPES_MESURE = [
    (c.DISTANCE, "Distance", "Distance entre deux points"),
    (c.DISTANCE_XYZ, "Distance XYZ", "Longueur, ΔX, ΔY, ΔZ, pente et angle en plan"),
    (c.CHAINE, "Chaîne", "Longueur cumulée d'une suite de points"),
    (c.SURFACE, "Surface", "Surface vraie, surface projetée, périmètre et pente d'un polygone"),
    (c.ANGLE, "Angle", "Angle entre deux bras (point, sommet, point)"),
]


def redessiner_vues(_self=None, context=None) -> None:
    """Demande le rafraîchissement de toutes les vues 3D (après un changement de réglage)."""
    gestionnaire = (context or bpy.context).window_manager
    if gestionnaire is None:
        return
    for fenetre in gestionnaire.windows:
        for zone in fenetre.screen.areas:
            if zone.type == "VIEW_3D":
                zone.tag_redraw()


class MP3D_Point(PropertyGroup):
    """Un point de mesure (coordonnées monde, unités Blender)."""

    co: FloatVectorProperty(name="Position", size=3, subtype="XYZ")


class MP3D_Mesure(PropertyGroup):
    """Une mesure enregistrée."""

    nom: StringProperty(name="Nom", default="Mesure", update=redessiner_vues)
    type: EnumProperty(name="Type", items=TYPES_MESURE, default=c.DISTANCE)
    points: CollectionProperty(type=MP3D_Point)
    visible: BoolProperty(name="Visible", default=True, update=redessiner_vues)
    nom_affiche: BoolProperty(name="Afficher le nom", description="Affiche le nom au-dessus de la valeur",
                              default=False, update=redessiner_vues)


class MP3D_Reglages(PropertyGroup):
    """Réglages et mesures d'une scène."""

    mesures: CollectionProperty(type=MP3D_Mesure)
    index_actif: IntProperty(name="Mesure active", default=0, update=redessiner_vues)
    compteur: IntProperty(default=0)

    unite: EnumProperty(name="Unité", items=[("m", "m", "Mètres"), ("cm", "cm", "Centimètres"),
                                             ("mm", "mm", "Millimètres")],
                        default="m", update=redessiner_vues)
    facteur: FloatProperty(
        name="Facteur de calibration", default=1.0, min=1e-9, soft_min=1e-6, precision=6,
        description="Multiplicateur appliqué à toutes les mesures (corrige un modèle importé à la mauvaise échelle)",
        update=redessiner_vues)
    source_calibration: StringProperty(name="Origine de la calibration", default="")
    repere: EnumProperty(
        name="Repère", default="GLOBAL", update=redessiner_vues,
        items=[("GLOBAL", "Global", "Axes X, Y, Z de la scène", "ORIENTATION_GLOBAL", 0),
               ("OBJET", "Objet", "Axes d'un objet de référence (bâtiment non aligné…)", "ORIENTATION_LOCAL", 1)])
    objet_repere: PointerProperty(name="Objet de référence", type=bpy.types.Object, update=redessiner_vues)

    afficher: BoolProperty(name="Afficher les mesures", default=True, update=redessiner_vues)
    afficher_composantes: BoolProperty(name="Afficher ΔX, ΔY, ΔZ",
                                       description="Dessine les composantes des distances XYZ en couleurs d'axes",
                                       default=True, update=redessiner_vues)


CLASSES = (MP3D_Point, MP3D_Mesure, MP3D_Reglages)


# ---------------------------------------------------------------------------
# Accès aux valeurs (utilisé par le dessin, les opérateurs et le panneau)
# ---------------------------------------------------------------------------

def reglages(scene: bpy.types.Scene) -> MP3D_Reglages:
    return scene.mesureplan3d


def metres_par_unite(scene: bpy.types.Scene) -> float:
    """Mètres réels par unité Blender : échelle de la scène × facteur de calibration."""
    return scene.unit_settings.scale_length * reglages(scene).facteur


def rotation_repere(scene: bpy.types.Scene) -> c.Matrice3 | None:
    """Matrice monde → repère choisi (None pour le repère global)."""
    r = reglages(scene)
    if r.repere != "OBJET" or r.objet_repere is None:
        return None
    # Rotation pure de l'objet (l'échelle et le cisaillement éventuels sont ignorés)
    matrice = r.objet_repere.matrix_world.to_quaternion().to_matrix().transposed()
    return tuple(tuple(ligne) for ligne in matrice)  # type: ignore[return-value]


def nom_repere(scene: bpy.types.Scene) -> str:
    r = reglages(scene)
    if r.repere == "OBJET" and r.objet_repere is not None:
        return f"Objet « {r.objet_repere.name} »"
    return "Global"


def points_monde(mesure: MP3D_Mesure) -> list[c.Vecteur]:
    return [tuple(p.co) for p in mesure.points]  # type: ignore[misc]


def valeurs_points(scene: bpy.types.Scene, type_mesure: str, points: list[c.Vecteur]) -> dict:
    """Valeurs réelles d'une liste de points monde."""
    f = metres_par_unite(scene)
    return c.valeurs(type_mesure, [c.multiplier(p, f) for p in points], rotation_repere(scene))


def valeurs_mesure(scene: bpy.types.Scene, mesure: MP3D_Mesure) -> dict | None:
    """Valeurs d'une mesure enregistrée (None si elle est incomplète)."""
    minimum = c.POINTS_FIXES.get(mesure.type, c.POINTS_MINIMUM.get(mesure.type, 2))
    if len(mesure.points) < minimum:
        return None
    return valeurs_points(scene, mesure.type, points_monde(mesure))


def formateur(scene: bpy.types.Scene, cfg: dict) -> c.Formateur:
    aff = cfg.get("affichage", {})
    return c.Formateur(unite=reglages(scene).unite, decimales=dict(aff.get("decimales", {"m": 2, "cm": 1, "mm": 0})),
                       decimales_surface=int(aff.get("decimales_surface", 2)),
                       decimales_angle=int(aff.get("decimales_angle", 1)))


def axes_repere(scene: bpy.types.Scene) -> tuple[c.Vecteur, c.Vecteur, c.Vecteur]:
    """Axes X, Y, Z du repère choisi, exprimés dans le monde (pour le verrouillage d'axe)."""
    rotation = rotation_repere(scene)
    if rotation is None:
        return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    return rotation  # lignes de la matrice monde → repère = axes du repère dans le monde

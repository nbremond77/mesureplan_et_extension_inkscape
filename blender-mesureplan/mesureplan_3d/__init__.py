"""MesurePlan 3D — mesures dans la vue 3D de Blender : distance, distance XYZ (ΔX, ΔY, ΔZ, pente),
chaîne, surface (vraie et projetée), angle, avec accrochage, calibration et export CSV.

Extension Blender 4.2+ (blender_manifest.toml). Le bloc bl_info permet aussi
l'installation comme « addon » classique dans Blender 4.0 et 4.1.
"""

bl_info = {
    "name": "MesurePlan 3D",
    "author": "Bernard",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "Vue 3D > Barre latérale (N) > MesurePlan",
    "description": "Mesures 3D : distance, ΔX/ΔY/ΔZ, pente, chaîne, surface, angle, calibration",
    "category": "3D View",
}

import bpy  # noqa: E402

from . import dessin, interface, operateurs, proprietes, socle  # noqa: E402

CLASSES = proprietes.CLASSES + operateurs.CLASSES + interface.CLASSES


def register() -> None:
    cfg = socle.charger_configuration(__package__)
    socle.configurer_journal(__package__, cfg.get("journalisation", {}))
    for classe in CLASSES:
        bpy.utils.register_class(classe)
    bpy.types.Scene.mesureplan3d = bpy.props.PointerProperty(type=proprietes.MP3D_Reglages)
    dessin.activer()
    socle.journal.info("MesurePlan 3D %s activé (Blender %s)", ".".join(map(str, bl_info["version"])),
                       bpy.app.version_string)


def unregister() -> None:
    dessin.desactiver()
    del bpy.types.Scene.mesureplan3d
    for classe in reversed(CLASSES):
        bpy.utils.unregister_class(classe)
    socle.journal.info("MesurePlan 3D désactivé")
    socle.fermer_journal()

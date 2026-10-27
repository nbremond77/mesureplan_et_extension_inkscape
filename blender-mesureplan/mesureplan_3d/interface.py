"""Panneaux de la barre latérale de la vue 3D (touche N), onglet « MesurePlan »."""

# Pas de « from __future__ import annotations » : Blender lit les annotations de propriétés
# (bpy.props) comme des objets ; converties en chaînes, elles ne seraient pas enregistrées.

import bpy
from bpy.types import Panel, UIList

from . import calcul3d as c, proprietes, socle

CATEGORIE = "MesurePlan"

# (type, libellé, icône) des boutons d'outils
OUTILS = [
    (c.DISTANCE, "Distance", "DRIVER_DISTANCE"),
    (c.DISTANCE_XYZ, "Distance XYZ", "EMPTY_AXIS"),
    (c.CHAINE, "Chaîne", "CURVE_PATH"),
    (c.SURFACE, "Surface", "MESH_PLANE"),
    (c.ANGLE, "Angle", "DRIVER_ROTATIONAL_DIFFERENCE"),
]


class MP3D_UL_mesures(UIList):
    """Liste des mesures : visibilité, nom modifiable, valeur."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0):
        ligne = layout.row(align=True)
        ligne.prop(item, "visible", text="", emboss=False, icon="HIDE_OFF" if item.visible else "HIDE_ON")
        ligne.prop(item, "nom", text="", emboss=False)
        v = proprietes.valeurs_mesure(context.scene, item)
        if v is not None:
            fmt = proprietes.formateur(context.scene, socle.charger_configuration(__package__))
            ligne.label(text=c.valeur_principale(item.type, v, fmt))


class MP3D_PT_outils(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORIE
    bl_label = "Mesurer"

    def draw(self, context):
        disposition = self.layout
        grille = disposition.grid_flow(columns=2, align=True)
        for type_mesure, libelle, icone in OUTILS:
            grille.operator("mesureplan3d.mesurer", text=libelle, icon=icone).type = type_mesure

        boite = disposition.box()
        boite.label(text="Depuis la sélection (mode Édition)", icon="EDITMODE_HLT")
        grille = boite.grid_flow(columns=2, align=True)
        grille.enabled = context.mode == "EDIT_MESH"
        for type_mesure, libelle, icone in OUTILS:
            grille.operator("mesureplan3d.depuis_selection", text=libelle, icon=icone).type = type_mesure

        r = proprietes.reglages(context.scene)
        colonne = disposition.column(align=True)
        colonne.prop(r, "unite")
        colonne.prop(r, "repere", expand=True)
        if r.repere == "OBJET":
            colonne.prop(r, "objet_repere", text="")
        colonne.separator()
        colonne.prop(r, "afficher")
        colonne.prop(r, "afficher_composantes")


class MP3D_PT_calibration(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORIE
    bl_label = "Échelle et calibration"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        disposition = self.layout
        scene = context.scene
        r = proprietes.reglages(scene)
        unites = scene.unit_settings
        disposition.label(text=f"Échelle de la scène : 1 unité = {unites.scale_length:g} m", icon="INFO")
        disposition.prop(r, "facteur")
        if r.source_calibration:
            disposition.label(text=r.source_calibration)
        ligne = disposition.row(align=True)
        ligne.operator("mesureplan3d.mesurer", text="Calibrer", icon="ARROW_LEFTRIGHT").type = c.CALIBRATION
        ligne.operator("mesureplan3d.reinitialiser_calibration", text="", icon="LOOP_BACK")
        disposition.operator("mesureplan3d.appliquer_calibration", icon="CHECKMARK")


class MP3D_PT_mesures(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORIE
    bl_label = "Mesures"

    def draw(self, context):
        disposition = self.layout
        scene = context.scene
        r = proprietes.reglages(scene)
        ligne = disposition.row()
        ligne.template_list("MP3D_UL_mesures", "", r, "mesures", r, "index_actif", rows=4)
        colonne = ligne.column(align=True)
        colonne.operator("mesureplan3d.cadrer", text="", icon="ZOOM_SELECTED")
        colonne.operator("mesureplan3d.supprimer", text="", icon="X")
        colonne.operator("mesureplan3d.tout_supprimer", text="", icon="TRASH")
        colonne.separator()
        colonne.operator("mesureplan3d.exporter_csv", text="", icon="EXPORT")

        if 0 <= r.index_actif < len(r.mesures):
            mesure = r.mesures[r.index_actif]
            v = proprietes.valeurs_mesure(scene, mesure)
            boite = disposition.box()
            entete = boite.row()
            entete.label(text=c.LIBELLES.get(mesure.type, mesure.type))
            entete.prop(mesure, "nom_affiche", text="Nom sur la vue")
            if v is not None:
                cfg = socle.charger_configuration(__package__)
                tolerance = float(cfg.get("affichage", {}).get("tolerance_planeite_m", 0.005))
                for texte in c.detail(mesure.type, v, proprietes.formateur(scene, cfg), tolerance):
                    boite.label(text=texte, icon="ERROR" if texte.startswith("⚠") else "NONE")
            boite.label(text=f"Repère : {proprietes.nom_repere(scene)}")


class MP3D_PT_aide(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORIE
    bl_label = "Aide"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        colonne = self.layout.column(align=True)
        for ligne in ("Clic : poser un point (accrochage auto)",
                      "Vert : sommet / point de mesure",
                      "Bleu : milieu · violet : arête",
                      "Orange : face · gris : point libre",
                      "Ctrl maintenu : sans accrochage",
                      "X / Y / Z : verrou d'axe (repère choisi)",
                      "Retour arrière : retirer le dernier point",
                      "Entrée / clic droit : terminer",
                      "Échap : quitter l'outil",
                      "Molette / bouton milieu : naviguer"):
            colonne.label(text=ligne)


CLASSES = (MP3D_UL_mesures, MP3D_PT_outils, MP3D_PT_calibration, MP3D_PT_mesures, MP3D_PT_aide)

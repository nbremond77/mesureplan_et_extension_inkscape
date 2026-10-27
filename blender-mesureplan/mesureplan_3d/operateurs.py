"""Opérateurs : outil de mesure modal, calibration, mesures depuis la sélection, gestion et export."""

# Pas de « from __future__ import annotations » : Blender lit les annotations de propriétés
# (bpy.props) comme des objets ; converties en chaînes, elles ne seraient pas enregistrées.

import logging
from pathlib import Path

import bmesh
import bpy
from bpy.props import EnumProperty, FloatProperty, StringProperty
from bpy_extras.io_utils import ExportHelper
from mathutils import Matrix, Vector

from . import accrochage, calcul3d as c, dessin, proprietes, socle

journal = logging.getLogger(socle.NOM_JOURNAL)

TYPES_OUTIL = proprietes.TYPES_MESURE + [(c.CALIBRATION, "Calibrer", "Calibrer sur une distance connue")]

# Évènements laissés à Blender pendant un tracé (navigation dans la vue)
NAVIGATION = {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "WHEELINMOUSE", "WHEELOUTMOUSE",
              "TRACKPADPAN", "TRACKPADZOOM", "NDOF_MOTION", "MOUSEROTATE", "MOUSESMARTZOOM"}
TOUCHES_AXE = {"X": 0, "Y": 1, "Z": 2}


def ajouter_mesure(scene, type_mesure: str, points: list) -> proprietes.MP3D_Mesure:
    """Crée une mesure enregistrée dans la scène et la rend active."""
    r = proprietes.reglages(scene)
    r.compteur += 1
    mesure = r.mesures.add()
    mesure.type = type_mesure
    mesure.nom = f"{c.LIBELLES[type_mesure]} {r.compteur}"
    for p in points:
        mesure.points.add().co = tuple(p)
    r.index_actif = len(r.mesures) - 1
    journal.info("Mesure ajoutée : %s (%d points)", mesure.nom, len(points))
    return mesure


def texte_resultat(scene, mesure) -> str:
    v = proprietes.valeurs_mesure(scene, mesure)
    if v is None:
        return mesure.nom
    cfg = socle.charger_configuration(__package__)
    return f"{mesure.nom} : {c.valeur_principale(mesure.type, v, proprietes.formateur(scene, cfg))}"


# ---------------------------------------------------------------------------
# Outil modal
# ---------------------------------------------------------------------------

class MP3D_OT_mesurer(bpy.types.Operator):
    """Mesurer dans la vue 3D avec accrochage aux sommets, milieux, arêtes et faces"""

    bl_idname = "mesureplan3d.mesurer"
    bl_label = "Mesurer"
    bl_options = {"REGISTER", "UNDO"}

    type: EnumProperty(name="Type", items=TYPES_OUTIL, default=c.DISTANCE)

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    # --- Cycle de vie ------------------------------------------------------
    def invoke(self, context, event):
        # La région de dessin de la vue 3D (l'opérateur peut être lancé depuis la barre latérale)
        self.region = next((r for r in context.area.regions if r.type == "WINDOW"), None)
        self.rv3d = context.space_data.region_3d if context.space_data else None
        if self.region is None or self.rv3d is None:
            self.report({"ERROR"}, "Vue 3D introuvable")
            return {"CANCELLED"}
        self.points: list[Vector] = []
        self.axe: int | None = None
        dessin.ETAT_OUTIL = {"type": self.type, "points": self.points, "courant": None, "nature": "libre"}
        context.window_manager.modal_handler_add(self)
        self._consigne(context)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        context.area.tag_redraw()
        if event.type in NAVIGATION or (event.type.startswith("NUMPAD_") and event.type != "NUMPAD_ENTER"):
            return {"PASS_THROUGH"}

        if event.type == "MOUSEMOVE":
            self._suivre(context, event)
        elif event.type == "LEFTMOUSE" and event.value == "PRESS":
            if not self._dans_la_vue(event):
                return {"PASS_THROUGH"}  # clic dans la barre latérale ou ailleurs
            self._suivre(context, event)
            courant = dessin.ETAT_OUTIL["courant"]
            if courant is not None and (not self.points or (courant - self.points[-1]).length > 1e-9):
                self.points.append(courant.copy())
                self.axe = None
            fixe = c.POINTS_FIXES.get(self.type)
            if fixe and len(self.points) >= fixe:
                return self._terminer(context)
            self._consigne(context)
        elif event.type in {"RET", "NUMPAD_ENTER"} and event.value == "PRESS":
            if self._valide():
                return self._terminer(context)
        elif event.type == "BACK_SPACE" and event.value == "PRESS":
            if self.points:
                self.points.pop()
            self._consigne(context)
        elif event.type in TOUCHES_AXE and event.value == "PRESS":
            indice = TOUCHES_AXE[event.type]
            self.axe = None if self.axe == indice else indice
            self._suivre(context, event)
            self._consigne(context)
        elif event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
            # Comme dans MesurePlan 2D : le clic droit termine un tracé valide, sinon annule
            if self.type in c.POINTS_MINIMUM and self._valide():
                return self._terminer(context)
            return self._annuler(context)
        return {"RUNNING_MODAL"}

    # --- Outils internes ---------------------------------------------------
    def _dans_la_vue(self, event) -> bool:
        r = self.region
        return r.x <= event.mouse_x < r.x + r.width and r.y <= event.mouse_y < r.y + r.height

    def _souris(self, event) -> tuple[float, float]:
        return (event.mouse_x - self.region.x, event.mouse_y - self.region.y)

    def _suivre(self, context, event) -> None:
        if not self._dans_la_vue(event):
            return
        cfg = socle.charger_configuration(__package__)
        axe = None
        if self.axe is not None and self.points:
            axe = proprietes.axes_repere(context.scene)[self.axe]
        p, nature = accrochage.accrocher(context, self.region, self.rv3d, self._souris(event), cfg,
                                         self.points, event.ctrl, axe)
        dessin.ETAT_OUTIL["courant"] = p
        dessin.ETAT_OUTIL["nature"] = nature

    def _valide(self) -> bool:
        return len(self.points) >= c.POINTS_FIXES.get(self.type, c.POINTS_MINIMUM.get(self.type, 2))

    def _consigne(self, context) -> None:
        axe = f" · verrou {'XYZ'[self.axe]}" if self.axe is not None else ""
        fin = " · Entrée / clic droit : terminer" if self.type in c.POINTS_MINIMUM else ""
        context.area.header_text_set(
            f"{c.LIBELLES[self.type]} — {len(self.points)} point(s){axe} · clic : point · Ctrl : sans accrochage · "
            f"X / Y / Z : verrou d'axe · Retour arrière : annuler le point{fin} · Échap : quitter")

    def _nettoyer(self, context) -> None:
        dessin.ETAT_OUTIL = None
        context.area.header_text_set(None)
        context.area.tag_redraw()

    def _annuler(self, context):
        self._nettoyer(context)
        return {"CANCELLED"}

    def _terminer(self, context):
        points = [tuple(p) for p in self.points]
        self._nettoyer(context)
        scene = context.scene
        if self.type == c.CALIBRATION:
            longueur = proprietes.valeurs_points(scene, c.DISTANCE, points)["longueur"]
            if longueur <= 0:
                self.report({"WARNING"}, "Distance nulle : calibration ignorée")
                return {"CANCELLED"}
            bpy.ops.mesureplan3d.saisir_calibration("INVOKE_DEFAULT", longueur_mesuree=longueur)
            return {"FINISHED"}
        mesure = ajouter_mesure(scene, self.type, points)
        self.report({"INFO"}, texte_resultat(scene, mesure))
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

class MP3D_OT_saisir_calibration(bpy.types.Operator):
    """Saisir la longueur réelle de la distance mesurée et recalculer le facteur de calibration"""

    bl_idname = "mesureplan3d.saisir_calibration"
    bl_label = "Calibration"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    longueur_mesuree: FloatProperty(name="Longueur mesurée (m)", options={"HIDDEN"})
    longueur_reelle: FloatProperty(name="Longueur réelle (m)", min=1e-6, precision=4, default=1.0)

    def invoke(self, context, event):
        self.longueur_reelle = round(self.longueur_mesuree, 4)
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        cfg = socle.charger_configuration(__package__)
        fmt = proprietes.formateur(context.scene, cfg)
        self.layout.label(text=f"Distance mesurée : {fmt.longueur(self.longueur_mesuree)}")
        self.layout.prop(self, "longueur_reelle")

    def execute(self, context):
        if self.longueur_mesuree <= 0:
            return {"CANCELLED"}
        r = proprietes.reglages(context.scene)
        ancien = r.facteur
        r.facteur = ancien * self.longueur_reelle / self.longueur_mesuree
        r.source_calibration = f"{self.longueur_mesuree:.4f} m mesurés = {self.longueur_reelle:.4f} m réels"
        journal.info("Calibration : facteur %.6f → %.6f", ancien, r.facteur)
        self.report({"INFO"}, f"Facteur de calibration : {r.facteur:.6f}")
        return {"FINISHED"}


class MP3D_OT_reinitialiser_calibration(bpy.types.Operator):
    """Revenir à l'échelle de la scène (facteur 1)"""

    bl_idname = "mesureplan3d.reinitialiser_calibration"
    bl_label = "Réinitialiser la calibration"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        r = proprietes.reglages(context.scene)
        r.facteur = 1.0
        r.source_calibration = ""
        return {"FINISHED"}


class MP3D_OT_appliquer_calibration(bpy.types.Operator):
    """Mettre à l'échelle les objets sélectionnés (autour du curseur 3D) avec le facteur de calibration,
    puis remettre le facteur à 1 : le modèle devient juste en vraie grandeur"""

    bl_idname = "mesureplan3d.appliquer_calibration"
    bl_label = "Appliquer aux objets sélectionnés"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and bool(context.selected_objects) \
            and abs(proprietes.reglages(context.scene).facteur - 1.0) > 1e-9

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        r = proprietes.reglages(context.scene)
        f = r.facteur
        pivot = context.scene.cursor.location.copy()
        transformation = Matrix.Translation(pivot) @ Matrix.Scale(f, 4) @ Matrix.Translation(-pivot)
        selection = set(context.selected_objects)
        # Un enfant dont le parent est aussi sélectionné suit son parent : ne pas l'agrandir deux fois
        racines = [o for o in selection if not any(p in selection for p in _parents(o))]
        for objet in racines:
            objet.matrix_world = transformation @ objet.matrix_world
        # Les mesures suivent le modèle (points monde mis à l'échelle autour du même pivot)
        for mesure in r.mesures:
            for point in mesure.points:
                point.co = c.mettre_a_l_echelle([tuple(point.co)], tuple(pivot), f)[0]
        r.facteur = 1.0
        r.source_calibration = f"échelle ×{f:.6f} appliquée à {len(racines)} objet(s)"
        journal.info("Calibration appliquée : ×%.6f sur %d objet(s)", f, len(racines))
        self.report({"INFO"}, f"Échelle ×{f:.6f} appliquée à {len(racines)} objet(s)")
        return {"FINISHED"}


def _parents(objet):
    p = objet.parent
    while p is not None:
        yield p
        p = p.parent


# ---------------------------------------------------------------------------
# Mesures depuis la sélection (mode Édition)
# ---------------------------------------------------------------------------

class MP3D_OT_depuis_selection(bpy.types.Operator):
    """Créer une mesure à partir des sommets ou faces sélectionnés (ordre de sélection respecté)"""

    bl_idname = "mesureplan3d.depuis_selection"
    bl_label = "Mesurer la sélection"
    bl_options = {"REGISTER", "UNDO"}

    type: EnumProperty(name="Type", items=proprietes.TYPES_MESURE, default=c.DISTANCE_XYZ)

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH" and context.edit_object is not None

    def execute(self, context):
        objet = context.edit_object
        bm = bmesh.from_edit_mesh(objet.data)
        monde = objet.matrix_world
        scene = context.scene
        if self.type == c.SURFACE:
            faces = [f for f in bm.faces if f.select]
            if faces:
                mesures = [ajouter_mesure(scene, c.SURFACE, [monde @ v.co for v in f.verts]) for f in faces[:200]]
                total = sum(proprietes.valeurs_mesure(scene, m)["surface"] for m in mesures)
                cfg = socle.charger_configuration(__package__)
                self.report({"INFO"}, f"{len(mesures)} face(s) — total {proprietes.formateur(scene, cfg).surface(total)}")
                return {"FINISHED"}
        # Sommets dans l'ordre de sélection (historique bmesh), complétés par les autres sélectionnés
        historique = [e for e in bm.select_history if isinstance(e, bmesh.types.BMVert) and e.select]
        autres = [v for v in bm.verts if v.select and v not in historique]
        sommets = historique + autres
        requis = c.POINTS_FIXES.get(self.type, c.POINTS_MINIMUM.get(self.type, 2))
        if len(sommets) < requis:
            self.report({"WARNING"}, f"Sélectionnez au moins {requis} sommets (ou des faces pour une surface)")
            return {"CANCELLED"}
        if self.type in (c.DISTANCE, c.DISTANCE_XYZ):
            sommets = sommets[:2]
        elif self.type == c.ANGLE:
            sommets = sommets[:3]
        if autres and self.type in (c.CHAINE, c.SURFACE, c.ANGLE) and len(sommets) > 2:
            self.report({"WARNING"}, "Ordre des sommets incertain : sélectionnez-les un par un (Maj+clic)")
        mesure = ajouter_mesure(scene, self.type, [monde @ v.co for v in sommets])
        self.report({"INFO"}, texte_resultat(scene, mesure))
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Gestion des mesures
# ---------------------------------------------------------------------------

class MP3D_OT_supprimer(bpy.types.Operator):
    """Supprimer la mesure active"""

    bl_idname = "mesureplan3d.supprimer"
    bl_label = "Supprimer la mesure"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        r = proprietes.reglages(context.scene)
        return 0 <= r.index_actif < len(r.mesures)

    def execute(self, context):
        r = proprietes.reglages(context.scene)
        r.mesures.remove(r.index_actif)
        r.index_actif = min(r.index_actif, len(r.mesures) - 1)
        return {"FINISHED"}


class MP3D_OT_tout_supprimer(bpy.types.Operator):
    """Supprimer toutes les mesures de la scène"""

    bl_idname = "mesureplan3d.tout_supprimer"
    bl_label = "Supprimer toutes les mesures"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return len(proprietes.reglages(context.scene).mesures) > 0

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        r = proprietes.reglages(context.scene)
        r.mesures.clear()
        r.index_actif = 0
        return {"FINISHED"}


class MP3D_OT_cadrer(bpy.types.Operator):
    """Centrer la vue 3D sur la mesure active"""

    bl_idname = "mesureplan3d.cadrer"
    bl_label = "Centrer la vue sur la mesure"

    @classmethod
    def poll(cls, context):
        r = proprietes.reglages(context.scene)
        return context.space_data is not None and context.space_data.type == "VIEW_3D" \
            and 0 <= r.index_actif < len(r.mesures)

    def execute(self, context):
        r = proprietes.reglages(context.scene)
        points = proprietes.points_monde(r.mesures[r.index_actif])
        if not points:
            return {"CANCELLED"}
        rv3d = context.space_data.region_3d
        rv3d.view_location = Vector(c.centroide(points))
        etendue = max((c.distance(a, b) for a in points for b in points), default=1.0)
        rv3d.view_distance = max(etendue * 1.8, 0.5)
        return {"FINISHED"}


class MP3D_OT_exporter_csv(bpy.types.Operator, ExportHelper):
    """Exporter toutes les mesures de la scène en CSV (séparateur « ; », virgule décimale)"""

    bl_idname = "mesureplan3d.exporter_csv"
    bl_label = "Exporter les mesures (CSV)"
    filename_ext = ".csv"
    filter_glob: StringProperty(default="*.csv", options={"HIDDEN"})

    def execute(self, context):
        scene = context.scene
        cfg = socle.charger_configuration(__package__)
        f = proprietes.metres_par_unite(scene)
        lignes = []
        for m in proprietes.reglages(scene).mesures:
            v = proprietes.valeurs_mesure(scene, m)
            if v is not None:
                lignes.append((m.nom, m.type, v, [c.multiplier(p, f) for p in proprietes.points_monde(m)]))
        export = cfg.get("export", {})
        try:
            n = c.exporter_csv(Path(self.filepath), lignes, proprietes.nom_repere(scene),
                               export.get("separateur_csv", ";"), export.get("separateur_decimal", ","))
        except OSError as erreur:
            journal.exception("Export CSV impossible : %s", self.filepath)
            self.report({"ERROR"}, f"Export impossible : {erreur}")
            return {"CANCELLED"}
        journal.info("Export CSV : %s (%d mesures)", self.filepath, n)
        self.report({"INFO"}, f"{n} mesure(s) exportée(s)")
        return {"FINISHED"}


CLASSES = (MP3D_OT_mesurer, MP3D_OT_saisir_calibration, MP3D_OT_reinitialiser_calibration,
           MP3D_OT_appliquer_calibration, MP3D_OT_depuis_selection, MP3D_OT_supprimer, MP3D_OT_tout_supprimer,
           MP3D_OT_cadrer, MP3D_OT_exporter_csv)

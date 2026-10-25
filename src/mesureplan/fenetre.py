"""Fenêtre principale : orchestration document / session / vue / panneaux."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (QDockWidget, QFileDialog, QInputDialog, QLabel, QMainWindow, QScrollArea,
                               QMessageBox, QSpinBox, QToolBar, QWidget)

from mesureplan import __version__
from mesureplan import annotations as ann
from mesureplan import export_pdf
from mesureplan import geometrie as geo
from mesureplan import impression_pdf
from mesureplan.annotations import Style, TypeAnnotation
from mesureplan.dialogue_impression import DialogueImpression, imprimer_pdf
from mesureplan.echelle import EchellePage, Reference, lire_denominateur
from mesureplan.icones import icone
from mesureplan.mesures import FACTEURS_UNITE, Formateur, Mesure, Session, TypeMesure, chemin_session_pour
from mesureplan.panneau_annotations import DialogueExportPDF, PanneauAnnotations
from mesureplan.panneaux import PanneauEchelle, PanneauMesures, _texte_echelle
from mesureplan.pdf_document import DocumentPDF
from mesureplan.vue_plan import ANNOTATION_PAR_OUTIL, Outil, VuePlan

journal = logging.getLogger(__name__)

# Correspondance outil → type de mesure du modèle
TYPE_PAR_OUTIL = {Outil.DISTANCE: TypeMesure.DISTANCE, Outil.CHAINE: TypeMesure.CHAINE,
                  Outil.SURFACE: TypeMesure.SURFACE, Outil.ANGLE: TypeMesure.ANGLE}

# (outil, nom d'icône, raccourci, info-bulle)
DEFINITION_OUTILS = [
    (Outil.NAVIGATION, "navigation", "N", "Naviguer (N ou Échap) — glisser pour déplacer, clic pour sélectionner"),
    (Outil.DISTANCE, "distance", "D", "Distance entre deux points (D)"),
    (Outil.CHAINE, "chaine", "L", "Chaîne de cotes cumulées (L) — double-clic, Entrée ou clic droit pour terminer"),
    (Outil.SURFACE, "surface", "S", "Surface et périmètre (S) — double-clic, Entrée ou clic droit pour fermer"),
    (Outil.ANGLE, "angle", "A", "Angle (A) — point du 1er bras, sommet, point du 2e bras"),
    (Outil.CALIBRATION, "calibrer", "C", "Calibrer sur une cote connue (C)"),
]

# Outils d'annotation : (outil, icône, raccourci, info-bulle)
DEFINITION_ANNOTATIONS = [
    (Outil.FLECHE, "fleche", "W", "Flèche (W) — glisser de la queue vers la pointe ; Maj : angle contraint"),
    (Outil.LIGNE, "ligne", "I", "Ligne (I) — glisser ; Maj : angle contraint"),
    (Outil.POLYLIGNE, "polyligne", "Y", "Polyligne (Y) — clics successifs, double-clic / Entrée pour terminer"),
    (Outil.POLYGONE, "polygone", "G", "Polygone (G) — clics successifs, double-clic / Entrée pour fermer"),
    (Outil.RECTANGLE, "rectangle", "Q", "Rectangle (Q) — glisser d'un coin à l'autre ; Maj : carré"),
    (Outil.ELLIPSE, "ellipse", "E", "Ovale (E) — glisser la boîte englobante ; Maj : cercle"),
    (Outil.CERCLE, "cercle", "O", "Cercle (O) — glisser du centre vers le bord"),
    (Outil.TEXTE, "texte", "T", "Texte (T) — clic à l'emplacement du coin haut-gauche"),
]
LIMITE_HISTORIQUE = 100

AIDE = """
<h3>MesurePlan {version}</h3>
<p><b>Outils</b> : N naviguer · D distance · L chaîne · S surface · A angle · C calibrer.
Le <b>clic droit</b> termine le tracé en cours (s'il est valide) et revient à l'outil Naviguer.</p>
<p><b>Édition (outil Naviguer)</b> : glisser une mesure ou une annotation la déplace (Maj :
horizontal / vertical) ; glisser une poignée carrée déplace le sommet, avec accrochage ; la poignée
ronde fait tourner rectangles, ovales, lignes et flèches (Maj : pas de 15°), l'angle se saisit aussi
dans le panneau <i>Annotations</i> ; Ctrl+clic sur une poignée supprime le sommet ; double-clic sur un
côté de chaîne, surface, polyligne ou polygone ajoute un sommet. Échap annule le glisser en cours.</p>
<p><b>Pendant un tracé</b><br>
• l'accrochage s'active automatiquement : ■ extrémité, ▲ milieu, ✕ intersection, ⧖ sur le trait<br>
• <b>Ctrl</b> maintenu : point libre (sans accrochage) · F3 : accrochage on/off<br>
• <b>Maj</b> maintenu : direction contrainte par pas de {pas}°<br>
• <b>Retour arrière</b> : retire le dernier point · <b>Échap</b> : annule le tracé<br>
• <b>Entrée</b>, double-clic ou clic droit : termine une chaîne ou une surface</p>
<p><b>Vue</b> : molette = zoom sous le curseur · bouton du milieu ou <b>Espace</b>+glisser = déplacer ·
F = toute la page · +/− = zoom · Pg.préc./Pg.suiv. = page</p>
<p><b>Échelle</b> : réglez l'échelle du cartouche (souvent lue automatiquement), puis calibrez sur une
ou plusieurs cotes écrites sur le plan (C). Toutes les mesures sont recalculées instantanément.</p>
<p><b>Annotations</b> : W flèche · I ligne · Y polyligne · G polygone · Q rectangle · E ovale ·
O cercle · T texte. Couleurs du trait et du fond (ou fond transparent), opacité, épaisseur, tirets et
taille du texte se règlent dans le panneau <i>Annotations</i> ; ils s'appliquent aussi à l'annotation
sélectionnée. En mode navigation : glisser une annotation la déplace, double-clic sur un texte le modifie.
<b>Ctrl+Maj+P</b> exporte une copie PDF annotée (incrustée ou en annotations PDF modifiables).
<b>Ctrl+Z / Ctrl+Y</b> : annuler / rétablir.</p>
<p><b>Ctrl+P : imprimer à l'échelle</b> (1:50, 1:100…) sur A4 à A0, Letter ou format personnalisé, en
mosaïque avec recouvrement si nécessaire. Chaque feuille porte une barre d'échelle et un segment de
contrôle de 100 mm : imprimez à 100 % (taille réelle), jamais « ajuster à la page ».</p>
<p><b>Mesures</b> : sélection par clic sur le plan ou dans le tableau · Suppr = supprimer ·
double-clic sur la valeur = zoomer · F2 sur le nom = renommer (le nom s'affiche alors sur le plan).
Les mesures sont enregistrées automatiquement à côté du PDF (<i>plan.pdf.mesures.json</i>).</p>
"""


class FenetrePrincipale(QMainWindow):
    """Fenêtre principale de MesurePlan."""

    def __init__(self, config: dict) -> None:
        super().__init__()
        self._cfg = config
        self._formateur = Formateur.depuis_config(config["affichage"])
        self._document: DocumentPDF | None = None
        self._session: Session | None = None
        self._chemin_session: Path | None = None
        self._page = 0
        self._selection: set[int] = set()
        self._outil_avant_calibration = Outil.NAVIGATION
        self._modifie = False
        self._pages_signalees_sans_traits: set[int] = set()
        self._historique: list[dict] = []   # états précédents (annuler)
        self._futur: list[dict] = []        # états annulés (rétablir)
        self._etat_courant: dict | None = None
        self._parametres = QSettings("MesurePlan", "MesurePlan")

        self.setWindowTitle("MesurePlan")
        self.setAcceptDrops(True)
        self._style = self._charger_style()

        # --- Vue centrale
        self.vue = VuePlan(config)
        self.vue.formateur_apercu = self._texte_apercu
        self.vue.mesure_terminee.connect(self._sur_mesure_terminee)
        self.vue.reference_tracee.connect(self._sur_reference_tracee)
        self.vue.position_changee.connect(self._sur_position)
        self.vue.outil_change.connect(self._sur_outil_change)
        self.vue.mesure_cliquee.connect(self._sur_mesure_cliquee)
        self.vue.style_annotation = lambda: self._style
        self.vue.annotation_tracee.connect(self._sur_annotation_tracee)
        self.vue.texte_demande.connect(self._sur_texte_demande)
        self.vue.geometrie_modifiee.connect(self._sur_geometrie_modifiee)
        self.vue.etiquette_mesure = self._etiquette_temporaire
        self.vue.element_double_clic.connect(self._sur_double_clic)
        self.setCentralWidget(self.vue)

        # --- Panneaux
        self.panneau_echelle = PanneauEchelle(config)
        self.panneau_echelle.denominateur_saisi.connect(self._sur_denominateur_saisi)
        self.panneau_echelle.demande_calibration.connect(lambda: self._choisir_outil(Outil.CALIBRATION))
        self.panneau_echelle.supprimer_reference.connect(self._sur_suppression_reference)
        self.panneau_echelle.effacer_references.connect(self._sur_effacement_references)
        self.panneau_echelle.appliquer_detection.connect(self._sur_application_detection)
        self.panneau_mesures = PanneauMesures(self._formateur)
        self.panneau_mesures.selection_changee.connect(self._sur_selection_tableau)
        self.panneau_mesures.renommage.connect(self._sur_renommage)
        self.panneau_mesures.suppression.connect(self._supprimer)
        self.panneau_mesures.cadrage.connect(self._sur_cadrage)
        self.panneau_mesures.unite_changee.connect(self._sur_unite)
        self.panneau_mesures.export_demande.connect(self.exporter_csv)
        self.panneau_annotations = PanneauAnnotations(self._style)
        self.panneau_annotations.style_change.connect(self._sur_style_change)
        self.panneau_annotations.orientation_saisie.connect(self._sur_orientation_saisie)
        # Panneau haut : défilement vertical si la fenêtre est petite
        defilement_annotations = QScrollArea()
        defilement_annotations.setWidgetResizable(True)
        defilement_annotations.setFrameShape(QScrollArea.Shape.NoFrame)
        defilement_annotations.setWidget(self.panneau_annotations)
        self.dock_echelle = self._ajouter_dock("Échelle", self.panneau_echelle, "dock_echelle")
        self.dock_mesures = self._ajouter_dock("Mesures", self.panneau_mesures, "dock_mesures")
        self.dock_annotations = self._ajouter_dock("Annotations", defilement_annotations, "dock_annotations")
        # Annotations en onglet avec l'échelle (peu utilisée une fois la calibration faite)
        self.tabifyDockWidget(self.dock_echelle, self.dock_annotations)
        self.dock_echelle.raise_()

        # --- Actions, barre d'outils, barre d'état
        self._creer_actions()
        self._creer_barre_etat()
        self._activer_commandes(False)

        geometrie = self._parametres.value("geometrie")
        if geometrie is not None:
            self.restoreGeometry(geometrie)
        else:
            self.resize(1440, 900)
        etat = self._parametres.value("etat")
        if etat is not None:
            self.restoreState(etat)

    # ------------------------------------------------------------------
    # Construction de l'interface
    # ------------------------------------------------------------------
    def _ajouter_dock(self, titre: str, widget: QWidget, nom_objet: str) -> QDockWidget:
        dock = QDockWidget(titre, self)
        dock.setObjectName(nom_objet)
        dock.setWidget(widget)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable
                         | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        dock.setMinimumWidth(330)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        return dock

    def _action(self, texte: str, raccourci: str | QKeySequence | None, slot, icone_nom: str | None = None,
                info: str | None = None) -> QAction:
        action = QAction(texte, self)
        if raccourci:
            action.setShortcut(QKeySequence(raccourci))
        if icone_nom:
            action.setIcon(icone(icone_nom))
        action.setToolTip(info or texte)
        action.triggered.connect(slot)
        self.addAction(action)  # raccourci actif même si l'action n'est pas en barre
        return action

    def _creer_actions(self) -> None:
        barre = QToolBar("Principal")
        barre.setObjectName("barre_principale")
        barre.setMovable(False)
        barre.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.addToolBar(barre)

        style = self.style()
        self.action_ouvrir = self._action("Ouvrir", QKeySequence.StandardKey.Open, self.ouvrir_dialogue,
                                          info="Ouvrir un plan PDF (Ctrl+O) — ou glisser-déposer le fichier")
        self.action_ouvrir.setIcon(style.standardIcon(style.StandardPixmap.SP_DialogOpenButton))
        self.action_enregistrer = self._action("Enregistrer", QKeySequence.StandardKey.Save,
                                               self.enregistrer_session, info="Enregistrer les mesures (Ctrl+S)")
        self.action_enregistrer.setIcon(style.standardIcon(style.StandardPixmap.SP_DialogSaveButton))
        self.action_export = self._action("Export CSV", "Ctrl+E", self.exporter_csv,
                                          info="Exporter toutes les mesures en CSV (Ctrl+E)")
        self.action_export.setIcon(style.standardIcon(style.StandardPixmap.SP_FileDialogDetailedView))
        self.action_export_pdf = self._action("Export PDF", "Ctrl+Shift+P", self.exporter_pdf, "pdf",
                                              "Exporter une copie du PDF avec annotations et mesures (Ctrl+Maj+P)")
        self.action_imprimer = self._action("Imprimer", QKeySequence.StandardKey.Print, self.imprimer_echelle,
                                            "imprimante", "Imprimer à l'échelle, en mosaïque si besoin (Ctrl+P)")
        barre.addActions([self.action_ouvrir, self.action_enregistrer, self.action_export, self.action_export_pdf,
                          self.action_imprimer])
        barre.addSeparator()
        self.action_annuler = self._action("Annuler", QKeySequence.StandardKey.Undo, self.annuler,
                                           info="Annuler la dernière modification (Ctrl+Z)")
        self.action_annuler.setIcon(style.standardIcon(style.StandardPixmap.SP_ArrowBack))
        self.action_retablir = self._action("Rétablir", "Ctrl+Y", self.retablir,
                                            info="Rétablir (Ctrl+Y ou Ctrl+Maj+Z)")
        self.action_retablir.setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
        self.action_retablir.setIcon(style.standardIcon(style.StandardPixmap.SP_ArrowForward))
        barre.addActions([self.action_annuler, self.action_retablir])
        barre.addSeparator()

        # Pages
        self.action_page_prec = self._action("Page préc.", QKeySequence.StandardKey.MoveToPreviousPage,
                                             lambda: self._aller_page(self._page - 1))
        self.action_page_prec.setIcon(style.standardIcon(style.StandardPixmap.SP_ArrowUp))
        self.spin_page = QSpinBox()
        self.spin_page.setPrefix("Page ")
        self.spin_page.setMinimum(1)
        self.spin_page.valueChanged.connect(lambda v: self._aller_page(v - 1))
        self.action_page_suiv = self._action("Page suiv.", QKeySequence.StandardKey.MoveToNextPage,
                                             lambda: self._aller_page(self._page + 1))
        self.action_page_suiv.setIcon(style.standardIcon(style.StandardPixmap.SP_ArrowDown))
        barre.addAction(self.action_page_prec)
        barre.addWidget(self.spin_page)
        barre.addAction(self.action_page_suiv)
        barre.addSeparator()

        # Outils exclusifs
        self.groupe_outils = QActionGroup(self)
        self.groupe_outils.setExclusive(True)
        self.actions_outils: dict[Outil, QAction] = {}
        for outil, nom_icone, raccourci, info in DEFINITION_OUTILS:
            action = self._action(outil.value, raccourci, lambda _c=False, o=outil: self._choisir_outil(o),
                                  nom_icone, info)
            action.setCheckable(True)
            self.groupe_outils.addAction(action)
            self.actions_outils[outil] = action
            barre.addAction(action)
        self.actions_outils[Outil.NAVIGATION].setChecked(True)
        barre.addSeparator()

        # Deuxième barre : outils d'annotation (icônes seules, info-bulles détaillées)
        self.addToolBarBreak()
        barre_annotations = QToolBar("Annotations")
        barre_annotations.setObjectName("barre_annotations")
        barre_annotations.setMovable(False)
        barre_annotations.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(barre_annotations)
        for outil, nom_icone, raccourci, info in DEFINITION_ANNOTATIONS:
            action = self._action(outil.value, raccourci, lambda _c=False, o=outil: self._choisir_outil(o),
                                  nom_icone, info)
            action.setCheckable(True)
            self.groupe_outils.addAction(action)
            self.actions_outils[outil] = action
            barre_annotations.addAction(action)

        self.action_ajuster = self._action("Ajuster", "F", self.vue.ajuster, "ajuster", "Voir toute la page (F)")
        self.action_aimant = self._action("Accrochage", "F3", self._basculer_accrochage, "aimant",
                                          "Accrochage aux traits du plan (F3) — Ctrl maintenu : désactivé ponctuellement")
        self.action_aimant.setCheckable(True)
        self.action_aimant.setChecked(self.vue.accrochage_actif)
        barre.addActions([self.action_ajuster, self.action_aimant])
        barre.addSeparator()

        self.action_supprimer = self._action("Supprimer", QKeySequence.StandardKey.Delete,
                                             lambda: self._supprimer(set(self._selection)),
                                             info="Supprimer les mesures et annotations sélectionnées (Suppr)")
        self.action_aide = self._action("Aide", QKeySequence.StandardKey.HelpContents, self._afficher_aide,
                                        info="Raccourcis et mode d'emploi (F1)")
        self.action_aide.setIcon(style.standardIcon(style.StandardPixmap.SP_DialogHelpButton))
        barre.addAction(self.action_aide)

    def _creer_barre_etat(self) -> None:
        self.label_position = QLabel()
        self.label_accrochage = QLabel()
        self.label_accrochage.setMinimumWidth(110)
        self.label_echelle = QLabel()
        for label in (self.label_position, self.label_accrochage, self.label_echelle):
            self.statusBar().addPermanentWidget(label)
        self.statusBar().showMessage("Ouvrez un plan PDF (Ctrl+O) ou glissez-le dans la fenêtre.")

    def _activer_commandes(self, actif: bool) -> None:
        for action in [self.action_enregistrer, self.action_export, self.action_export_pdf, self.action_imprimer,
                       self.action_page_prec,
                       self.action_page_suiv, self.action_ajuster, self.action_supprimer,
                       *self.actions_outils.values()]:
            action.setEnabled(actif)
        self.spin_page.setEnabled(actif)
        self.panneau_echelle.setEnabled(actif)
        self.panneau_mesures.setEnabled(actif)
        self._maj_actions_historique()

    # ------------------------------------------------------------------
    # Ouverture / enregistrement
    # ------------------------------------------------------------------
    def ouvrir_dialogue(self) -> None:
        dossier = str(self._parametres.value("dernier_dossier", str(Path.home())))
        chemin, _filtre = QFileDialog.getOpenFileName(self, "Ouvrir un plan PDF", dossier, "Plans PDF (*.pdf)")
        if chemin:
            self.ouvrir_pdf(Path(chemin))

    def ouvrir_pdf(self, chemin: Path) -> None:
        """Ouvre un PDF et recharge la session de mesures associée si elle existe."""
        if not self._confirmer_abandon():
            return
        try:
            document = DocumentPDF(chemin)
        except Exception as erreur:
            journal.exception("Ouverture impossible : %s", chemin)
            QMessageBox.critical(self, "Ouverture impossible", f"{chemin.name}\n\n{erreur}")
            return
        if self._document is not None:
            self._document.fermer()
        self._document = document
        self._parametres.setValue("dernier_dossier", str(chemin.parent))

        suffixe = self._cfg["session"].get("suffixe_fichier", ".mesures.json")
        self._chemin_session = chemin_session_pour(chemin, suffixe)
        denominateur_defaut = float(self._cfg["echelle"].get("denominateur_defaut", 100))
        self._session = Session(str(chemin), denominateur_defaut)
        if self._chemin_session.exists():
            try:
                self._session = Session.charger(self._chemin_session)
                self.statusBar().showMessage(f"{len(self._session.mesures)} mesure(s) rechargée(s) "
                                             f"depuis {self._chemin_session.name}", 8000)
            except Exception as erreur:
                journal.exception("Session illisible : %s", self._chemin_session)
                QMessageBox.warning(self, "Session illisible",
                                    f"Les mesures enregistrées n'ont pas pu être relues :\n{erreur}\n\n"
                                    "Une nouvelle session est ouverte (l'ancien fichier sera remplacé "
                                    "à la prochaine sauvegarde).")
        self._modifie = False
        self._selection.clear()
        self._pages_signalees_sans_traits.clear()
        self.setWindowTitle(f"MesurePlan — {chemin.name}")
        self.spin_page.blockSignals(True)
        self.spin_page.setMaximum(document.nombre_pages)
        self.spin_page.setSuffix(f" / {document.nombre_pages}")
        self.spin_page.setValue(1)
        self.spin_page.blockSignals(False)
        self._historique.clear()
        self._futur.clear()
        self._etat_courant = self._session.vers_dict()
        self._activer_commandes(True)
        self._page = -1
        self._aller_page(0)

    def _confirmer_abandon(self) -> bool:
        """En l'absence de sauvegarde automatique, propose d'enregistrer avant de quitter le plan."""
        if not self._modifie or self._session is None:
            return True
        reponse = QMessageBox.question(
            self, "Mesures non enregistrées", "Enregistrer les mesures avant de continuer ?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        if reponse == QMessageBox.StandardButton.Save:
            return self.enregistrer_session()
        return reponse == QMessageBox.StandardButton.Discard

    def enregistrer_session(self) -> bool:
        if self._session is None or self._chemin_session is None:
            return False
        try:
            self._session.enregistrer(self._chemin_session)
        except OSError as erreur:
            journal.exception("Enregistrement impossible : %s", self._chemin_session)
            QMessageBox.warning(self, "Enregistrement impossible",
                                f"{self._chemin_session}\n\n{erreur}\n\nDossier du PDF en lecture seule ?")
            return False
        self._modifie = False
        self.statusBar().showMessage(f"Mesures enregistrées dans {self._chemin_session.name}", 4000)
        return True

    def exporter_csv(self) -> None:
        if self._session is None:
            return
        proposition = str(Path(self._session.chemin_pdf).with_name(Path(self._session.chemin_pdf).stem
                                                                   + "_mesures.csv"))
        chemin, _filtre = QFileDialog.getSaveFileName(self, "Exporter les mesures", proposition, "CSV (*.csv)")
        if not chemin:
            return
        cfg = self._cfg["export"]
        try:
            n = self._session.exporter_csv(Path(chemin), self._formateur, cfg.get("separateur_csv", ";"),
                                           cfg.get("separateur_decimal", ","), cfg.get("encodage", "utf-8-sig"))
        except OSError as erreur:
            journal.exception("Export CSV impossible : %s", chemin)
            QMessageBox.warning(self, "Export impossible", str(erreur))
            return
        self.statusBar().showMessage(f"{n} mesure(s) exportée(s) vers {Path(chemin).name}", 6000)

    def _apres_modification(self) -> None:
        """Rafraîchit l'affichage et sauvegarde automatiquement si configuré."""
        self._modifie = True
        if self._session is not None:
            # Historique : on empile l'état d'avant la modification
            if self._etat_courant is not None:
                self._historique.append(self._etat_courant)
                del self._historique[:-LIMITE_HISTORIQUE]
            self._etat_courant = self._session.vers_dict()
            self._futur.clear()
            self._maj_actions_historique()
        self._rafraichir()
        if self._cfg["session"].get("sauvegarde_auto", True):
            self.enregistrer_session()

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------
    def _aller_page(self, numero: int) -> None:
        if self._document is None or not 0 <= numero < self._document.nombre_pages or numero == self._page:
            return
        self._page = numero
        self._selection.clear()
        self.spin_page.blockSignals(True)
        self.spin_page.setValue(numero + 1)
        self.spin_page.blockSignals(False)
        self.vue.charger_page(self._document, numero)

        # Première visite de la page : échelle lue dans le cartouche si possible
        if numero not in self._session.echelles:
            echelle = self._session.echelle(numero)
            detection = self._document.detection_echelle(numero)
            if detection and self._cfg["echelle"].get("detection_automatique", True):
                echelle.denominateur_cartouche = detection.denominateur
                echelle.origine_cartouche = "lue sur le plan"
                self.statusBar().showMessage(
                    f"Échelle {_texte_echelle(detection.denominateur)} lue dans le cartouche — "
                    "vérifiez-la en calibrant sur une cote connue (C).", 10000)
            else:
                self.statusBar().showMessage(
                    "Aucune échelle lue dans le cartouche : saisissez-la dans le panneau Échelle.", 10000)
        if self.vue.nombre_traits == 0 and numero not in self._pages_signalees_sans_traits:
            self._pages_signalees_sans_traits.add(numero)
            QMessageBox.information(self, "Plan sans traits vectoriels",
                                    "Aucun trait vectoriel n'a été trouvé sur cette page (plan scanné ?).\n"
                                    "Les mesures restent possibles, mais sans accrochage : "
                                    "la précision dépend de votre pointage.")
        self._rafraichir()

    # ------------------------------------------------------------------
    # Rafraîchissement
    # ------------------------------------------------------------------
    def _echelle(self) -> EchellePage:
        return self._session.echelle(self._page)

    def _rafraichir(self) -> None:
        if self._session is None or self._document is None:
            return
        echelle = self._echelle()
        mesures = self._session.mesures_page(self._page)
        self.vue.afficher_mesures(
            [(m.identifiant, m.type.value, m.points, self._formateur.etiquette(m, echelle)) for m in mesures],
            [([r.p1, r.p2], f"Réf. {self._formateur.longueur(r.longueur_reelle_m)}") for r in echelle.references],
            self._selection, self._session.annotations_page(self._page))
        self.panneau_echelle.actualiser(echelle, self._document.detection_echelle(self._page), self._formateur)
        self.panneau_mesures.actualiser(mesures, echelle, self._formateur, self._selection)
        # Orientation affichée pour une annotation orientable sélectionnée seule
        orientation = None
        if len(self._selection) == 1:
            unique = self._session.annotation(next(iter(self._selection)))
            orientation = unique.orientation if unique is not None else None
        self.panneau_annotations.definir_orientation(orientation)
        etat = "✔" if echelle.est_calibree else "⚠ non vérifiée"
        self.label_echelle.setText(f"Échelle {_texte_echelle(echelle.denominateur_effectif)} {etat}")

    def _texte_apercu(self, outil: Outil, points: list[geo.Point]) -> str:
        """Valeur affichée en direct près du curseur pendant le tracé."""
        echelle = self._echelle()
        f = self._formateur
        if outil in (Outil.DISTANCE, Outil.CALIBRATION):
            texte = f.longueur(echelle.longueur_m(geo.distance(points[0], points[-1])))
            return texte + ("\n(au cartouche)" if outil is Outil.CALIBRATION else "")
        if outil is Outil.CHAINE:
            dernier = f.longueur(echelle.longueur_m(geo.distance(points[-2], points[-1])))
            return f"{dernier}\nΣ {f.longueur(echelle.longueur_m(geo.longueur_polyligne(points)))}"
        if outil is Outil.SURFACE:
            if len(points) < 3:
                return f.longueur(echelle.longueur_m(geo.distance(points[0], points[-1])))
            return (f"{f.surface(echelle.surface_m2(geo.aire_polygone(points)))}\n"
                    f"P {f.longueur(echelle.longueur_m(geo.longueur_polyligne(points, fermee=True)))}")
        if outil is Outil.ANGLE:
            if len(points) < 3:
                return f.longueur(echelle.longueur_m(geo.distance(points[0], points[-1])))
            return f.angle(geo.angle_trois_points(*points[:3]))
        return ""

    # ------------------------------------------------------------------
    # Réactions aux outils
    # ------------------------------------------------------------------
    def _choisir_outil(self, outil: Outil) -> None:
        if self._document is None:
            return
        if outil is Outil.CALIBRATION and self.vue.outil is not Outil.CALIBRATION:
            self._outil_avant_calibration = self.vue.outil
        self.vue.definir_outil(outil)
        if outil in ANNOTATION_PAR_OUTIL:
            self.dock_annotations.raise_()
        self.vue.setFocus()

    def _sur_outil_change(self, outil: Outil) -> None:
        self.actions_outils[outil].setChecked(True)
        consignes = {
            Outil.NAVIGATION: "Clic : sélection · glisser un élément : déplacer · poignées : sommets / rotation · "
                              "glisser le fond : se déplacer · molette : zoom",
            Outil.DISTANCE: "Distance : cliquez deux points (Maj = direction contrainte, Ctrl = sans accrochage)",
            Outil.CHAINE: "Chaîne : cliquez les points, terminez par double-clic, Entrée ou clic droit",
            Outil.SURFACE: "Surface : cliquez les sommets du contour, fermez par double-clic, Entrée ou clic droit",
            Outil.ANGLE: "Angle : point du premier bras, sommet, point du second bras",
            Outil.CALIBRATION: "Calibration : cliquez les deux extrémités d'une cote dont vous connaissez la valeur",
        }
        consignes.update({o: info for o, _icone, _r, info in DEFINITION_ANNOTATIONS})
        self.statusBar().showMessage(consignes[outil])

    def _basculer_accrochage(self) -> None:
        self.vue.accrochage_actif = self.action_aimant.isChecked()
        self.statusBar().showMessage("Accrochage " + ("activé" if self.vue.accrochage_actif else "désactivé"), 3000)

    def _sur_position(self, x: float, y: float, nature: str) -> None:
        if self._session is None:
            return
        f = self._echelle().facteur
        # Coordonnées réelles depuis le coin haut-gauche de la page (Y vers le bas)
        self.label_position.setText(f"x {self._formateur.longueur(x * f)}   y {self._formateur.longueur(y * f)}")
        self.label_accrochage.setText(f"⌖ {nature}")

    def _sur_mesure_terminee(self, outil: Outil, points: list[geo.Point]) -> None:
        mesure = self._session.ajouter_mesure(TYPE_PAR_OUTIL[outil], self._page, points)
        self._selection = {mesure.identifiant}
        self._apres_modification()
        texte = self._formateur.valeur_principale(mesure, self._echelle())
        message = f"{mesure.nom} : {texte}"
        if mesure.avertissement:
            message += f"  ⚠ {mesure.avertissement}"
        self.statusBar().showMessage(message, 8000)

    def _sur_reference_tracee(self, points: list[geo.Point]) -> None:
        """Demande la cote réelle de la référence tracée et recalcule l'échelle."""
        echelle = self._echelle()
        longueur_pt = geo.distance(points[0], points[1])
        if longueur_pt < 1e-6:
            return
        unite = self._formateur.unite_longueur
        facteur_unite = FACTEURS_UNITE[unite]
        au_cartouche_m = longueur_pt * echelle.facteur_cartouche
        decimales = {"m": 3, "cm": 1, "mm": 0}[unite]
        valeur, ok = QInputDialog.getDouble(
            self, "Cote de référence",
            f"Longueur tracée, à l'échelle du cartouche {_texte_echelle(echelle.denominateur_cartouche)} : "
            f"{self._formateur.longueur(au_cartouche_m)}\n\n"
            f"Saisissez la cote réelle écrite sur le plan (en {unite}) :",
            round(au_cartouche_m * facteur_unite, decimales), 0.0, 1e7, decimales)
        if ok and valeur > 0:
            echelle.references.append(Reference(points[0], points[1], valeur / facteur_unite))
            journal.info("Référence ajoutée page %d : %.4f m pour %.2f pt → échelle 1:%.2f",
                         self._page + 1, valeur / facteur_unite, longueur_pt, echelle.denominateur_effectif)
            self._apres_modification()
            ecart = echelle.ecart_cartouche_pct or 0.0
            self.statusBar().showMessage(
                f"Échelle calibrée : {_texte_echelle(echelle.denominateur_effectif)} "
                f"(écart {ecart:+.2f} % par rapport au cartouche)".replace(".", ","), 10000)
        # Retour à l'outil utilisé avant la calibration
        self._choisir_outil(self._outil_avant_calibration)

    # ------------------------------------------------------------------
    # Réactions aux panneaux
    # ------------------------------------------------------------------
    def _sur_denominateur_saisi(self, texte: str) -> None:
        try:
            denominateur = lire_denominateur(texte)
        except ValueError as erreur:
            self.statusBar().showMessage(str(erreur), 6000)
            self._rafraichir()
            return
        echelle = self._echelle()
        if abs(denominateur - echelle.denominateur_cartouche) < 1e-9:
            return
        echelle.denominateur_cartouche = denominateur
        echelle.origine_cartouche = "saisie"
        if echelle.est_calibree:
            self.statusBar().showMessage("Cartouche modifié : les mesures restent calculées avec la calibration "
                                         "(seul l'écart affiché change).", 8000)
        self._apres_modification()

    def _sur_application_detection(self) -> None:
        detection = self._document.detection_echelle(self._page) if self._document else None
        if detection:
            echelle = self._echelle()
            echelle.denominateur_cartouche = detection.denominateur
            echelle.origine_cartouche = "lue sur le plan"
            self._apres_modification()

    def _sur_suppression_reference(self, rang: int) -> None:
        echelle = self._echelle()
        if 0 <= rang < len(echelle.references):
            del echelle.references[rang]
            self._apres_modification()

    def _sur_effacement_references(self) -> None:
        if self._echelle().references:
            self._echelle().references.clear()
            self._apres_modification()

    def _sur_selection_tableau(self, identifiants: set[int]) -> None:
        self._selection = set(identifiants)
        self._rafraichir()

    def _sur_mesure_cliquee(self, identifiant: int) -> None:
        self._selection = {identifiant} if identifiant >= 0 else set()
        annotation = self._session.annotation(identifiant) if self._session and identifiant >= 0 else None
        if annotation is not None:
            # Édition du style de l'annotation sélectionnée depuis le panneau
            self.panneau_annotations.charger(annotation.style)
            self._style = annotation.style.copie()  # le prochain tracé reprend ce style
            self.dock_annotations.raise_()
        self._rafraichir()

    # ------------------------------------------------------------------
    # Annotations
    # ------------------------------------------------------------------
    def _charger_style(self) -> Style:
        """Dernier style utilisé (mémorisé entre deux sessions)."""
        texte = self._parametres.value("style_annotation")
        if texte:
            try:
                return Style.depuis_dict(json.loads(str(texte)))
            except (ValueError, TypeError):
                journal.warning("Style d'annotation mémorisé illisible : valeurs par défaut")
        return Style(couleur_trait=self._cfg["affichage"].get("couleur_apercu", "#D81B60"))

    def _sur_style_change(self, style: Style) -> None:
        self._style = style
        self._parametres.setValue("style_annotation", json.dumps(style.vers_dict()))
        selection = [a for a in self._session.annotations_page(self._page) if a.identifiant in self._selection] \
            if self._session else []
        if selection:
            for a in selection:
                a.style = style.copie()
            self._apres_modification()

    def _sur_annotation_tracee(self, type_annotation: TypeAnnotation, points: list[geo.Point]) -> None:
        a = self._session.ajouter_annotation(type_annotation, self._page, points, self._style)
        self._selection = {a.identifiant}
        self._apres_modification()

    def _sur_texte_demande(self, point: geo.Point) -> None:
        texte, ok = QInputDialog.getMultiLineText(self, "Texte", "Texte de l'annotation (plusieurs lignes possibles) :")
        if ok and texte.strip():
            a = self._session.ajouter_annotation(TypeAnnotation.TEXTE, self._page, [point], self._style,
                                                 texte.rstrip())
            self._selection = {a.identifiant}
            self._apres_modification()
        self.vue.setFocus()

    def _sur_geometrie_modifiee(self, identifiant: int, points: list, angle: float | None) -> None:
        """Déplacement, édition de sommet, rotation ou ajout/suppression de sommet (mesure ou annotation)."""
        points = [tuple(p) for p in points]
        annotation = self._session.annotation(identifiant)
        if annotation is not None:
            annotation.points = points
            if angle is not None:
                annotation.angle = angle
        else:
            mesure = self._session.mesure(identifiant)
            if mesure is None:
                return
            mesure.points = points
            self.statusBar().showMessage(f"{mesure.nom} : {self._formateur.valeur_principale(mesure, self._echelle())}",
                                         6000)
        self._selection = {identifiant}
        self._apres_modification()

    def _etiquette_temporaire(self, identifiant: int, points: list) -> str:
        """Valeur recalculée en direct pendant l'édition d'une mesure."""
        m = self._session.mesure(identifiant) if self._session else None
        if m is None:
            return ""
        copie = Mesure(m.identifiant, m.type, m.page, list(points), m.nom, m.nom_personnalise)
        return self._formateur.etiquette(copie, self._echelle())

    def _sur_orientation_saisie(self, angle: float) -> None:
        cibles = [a for a in self._session.annotations_page(self._page)
                  if a.identifiant in self._selection and a.orientation is not None] if self._session else []
        for a in cibles:
            a.definir_orientation(angle)
        if cibles:
            self._apres_modification()

    def _sur_double_clic(self, identifiant: int) -> None:
        """Double-clic : modifier le texte d'une annotation, ou renommer une mesure."""
        annotation = self._session.annotation(identifiant)
        if annotation is not None and annotation.type is TypeAnnotation.TEXTE:
            texte, ok = QInputDialog.getMultiLineText(self, "Modifier le texte", "Texte :", annotation.texte)
            if ok and texte.strip() and texte.rstrip() != annotation.texte:
                annotation.texte = texte.rstrip()
                self._apres_modification()
            return
        mesure = self._session.mesure(identifiant)
        if mesure is not None:
            nom, ok = QInputDialog.getText(self, "Renommer la mesure", "Nom (affiché sur le plan) :", text=mesure.nom)
            if ok:
                self._sur_renommage(identifiant, nom.strip())

    # ------------------------------------------------------------------
    # Annuler / rétablir
    # ------------------------------------------------------------------
    def _maj_actions_historique(self) -> None:
        self.action_annuler.setEnabled(bool(self._historique))
        self.action_retablir.setEnabled(bool(self._futur))

    def _restaurer(self, etat: dict) -> None:
        self._session = Session.depuis_dict(etat)
        self._etat_courant = etat
        existants = {m.identifiant for m in self._session.mesures} | {a.identifiant for a in self._session.annotations}
        self._selection &= existants
        self._modifie = True
        self._maj_actions_historique()
        self._rafraichir()
        if self._cfg["session"].get("sauvegarde_auto", True):
            self.enregistrer_session()

    def annuler(self) -> None:
        if self._historique and self._session is not None:
            self._futur.append(self._etat_courant)
            self._restaurer(self._historique.pop())
            self.statusBar().showMessage("Modification annulée", 2500)

    def retablir(self) -> None:
        if self._futur and self._session is not None:
            self._historique.append(self._etat_courant)
            self._restaurer(self._futur.pop())
            self.statusBar().showMessage("Modification rétablie", 2500)

    # ------------------------------------------------------------------
    # Export PDF annoté et impression à l'échelle
    # ------------------------------------------------------------------
    def _elements_par_page(self, annotations: bool, mesures: bool, references: bool,
                           pages: list[int] | None = None) -> dict[int, list]:
        """Éléments à dessiner par page : mesures (dessous), références, puis annotations (dessus)."""
        couleur_mesures = self._cfg["affichage"]["couleur_mesures"]
        couleur_references = self._cfg["affichage"]["couleur_references"]
        par_page: dict[int, list] = {}
        for page in pages if pages is not None else range(self._document.nombre_pages):
            echelle = self._session.echelles.get(page)
            elements = []
            if mesures and echelle is not None:
                for m in self._session.mesures_page(page):
                    elements += ann.primitives_mesure(m, echelle, self._formateur, couleur_mesures)
            if references and echelle is not None:
                for r in echelle.references:
                    style_ref = Style(couleur_trait=couleur_references, epaisseur=0.8, trait="tirets")
                    elements.append(ann.Annotation(0, TypeAnnotation.LIGNE, page, [r.p1, r.p2], style_ref))
            if annotations:
                elements += self._session.annotations_page(page)
            if elements:
                par_page[page] = elements
        return par_page

    def imprimer_echelle(self) -> None:
        """Impression de la page courante à une échelle choisie, sur un format de papier choisi."""
        if self._session is None or self._document is None:
            return
        echelle = self._echelle()
        largeur, hauteur = self._document.taille_page(self._page)
        x0, y0 = self._document.origine_page(self._page)
        source = Path(self._session.chemin_pdf)
        dialogue = DialogueImpression(
            {"page": (x0, y0, x0 + largeur, y0 + hauteur), "vue": self.vue.zone_visible()},
            echelle.facteur, echelle.est_calibree, round(echelle.denominateur_cartouche, 2),
            self._cfg["echelle"].get("echelles_proposees", [50, 100, 200]),
            source.with_name(f"{source.stem}_impression_p{self._page + 1}.pdf"), self)
        if not dialogue.exec() or dialogue.plan is None:
            return
        sortie = dialogue.chemin
        if sortie.resolve() == source.resolve():
            QMessageBox.warning(self, "Impression impossible", "Choisissez un fichier différent du plan d'origine.")
            return
        par_page = self._elements_par_page(dialogue.case_annotations.isChecked(), dialogue.case_mesures.isChecked(),
                                           False, pages=[self._page])
        titre = f"{source.name} — page {self._page + 1}"
        try:
            nombre = impression_pdf.generer(source, sortie, self._page, dialogue.plan, par_page, titre,
                                            dialogue.options)
        except Exception as erreur:
            journal.exception("Génération du PDF d'impression impossible : %s", sortie)
            QMessageBox.critical(self, "Impression impossible", f"{sortie}\n\n{erreur}")
            return
        plan = dialogue.plan
        self.statusBar().showMessage(f"PDF d'impression créé : {sortie.name} ({nombre} page(s), "
                                     f"{plan.format} {plan.orientation}, 1:{plan.denominateur:g})", 10000)
        if dialogue.action == "imprimer":
            try:
                if imprimer_pdf(self, sortie, plan, titre):
                    self.statusBar().showMessage(f"Impression envoyée — vérifiez le segment de contrôle "
                                                 f"de 100 mm. PDF conservé : {sortie.name}", 10000)
            except Exception as erreur:
                journal.exception("Impression directe impossible")
                QMessageBox.critical(self, "Impression impossible",
                                     f"{erreur}\n\nLe PDF d'impression est disponible : {sortie}")
        elif dialogue.case_ouvrir.isChecked():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(sortie)))
    def exporter_pdf(self) -> None:
        if self._session is None or self._document is None:
            return
        source = Path(self._session.chemin_pdf)
        dialogue = DialogueExportPDF(source.with_name(source.stem + "_annote.pdf"), self)
        if not dialogue.exec():
            return
        sortie = dialogue.chemin
        if sortie.resolve() == source.resolve():
            QMessageBox.warning(self, "Export impossible", "Choisissez un fichier différent du plan d'origine.")
            return
        if sortie.exists() and QMessageBox.question(self, "Fichier existant", f"Remplacer {sortie.name} ?") \
                != QMessageBox.StandardButton.Yes:
            return

        par_page = self._elements_par_page(dialogue.case_annotations.isChecked(), dialogue.case_mesures.isChecked(),
                                           dialogue.case_references.isChecked())
        if not par_page:
            QMessageBox.information(self, "Rien à exporter", "Aucune annotation ni mesure à ajouter au PDF.")
            return
        try:
            compteurs = export_pdf.exporter(source, sortie, par_page, dialogue.mode)
        except Exception as erreur:
            journal.exception("Export PDF impossible : %s", sortie)
            QMessageBox.critical(self, "Export impossible", f"{sortie}\n\n{erreur}")
            return
        message = (f"PDF annoté enregistré : {sortie.name} — {compteurs['incrustées']} élément(s) incrusté(s), "
                   f"{compteurs['annotations']} annotation(s) PDF")
        if compteurs["échecs"]:
            message += f", {compteurs['échecs']} échec(s) (voir le journal)"
        self.statusBar().showMessage(message, 10000)
        if dialogue.case_ouvrir.isChecked():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(sortie)))

    def _sur_renommage(self, identifiant: int, nom: str) -> None:
        mesure = self._session.mesure(identifiant)
        if mesure is None or not nom or nom == mesure.nom:
            return
        mesure.nom = nom
        mesure.nom_personnalise = True
        self._apres_modification()

    def _sur_cadrage(self, identifiant: int) -> None:
        mesure = self._session.mesure(identifiant)
        if mesure:
            self.vue.cadrer(mesure.points)

    def _sur_unite(self, unite: str) -> None:
        self._formateur.unite_longueur = unite
        self._rafraichir()

    def _supprimer(self, identifiants: set[int]) -> None:
        if not identifiants or self._session is None:
            return
        n = self._session.supprimer_mesures(identifiants)
        self._selection -= identifiants
        self._apres_modification()
        self.statusBar().showMessage(f"{n} mesure(s) supprimée(s)", 4000)

    def _afficher_aide(self) -> None:
        QMessageBox.about(self, "Aide — MesurePlan",
                          AIDE.format(version=__version__,
                                      pas=int(self._cfg["contrainte"].get("pas_angle_degres", 45))))

    # ------------------------------------------------------------------
    # Glisser-déposer et fermeture
    # ------------------------------------------------------------------
    def dragEnterEvent(self, evenement) -> None:  # noqa: N802
        urls = evenement.mimeData().urls()
        if urls and urls[0].toLocalFile().lower().endswith(".pdf"):
            evenement.acceptProposedAction()

    def dropEvent(self, evenement) -> None:  # noqa: N802
        urls = evenement.mimeData().urls()
        if urls:
            self.ouvrir_pdf(Path(urls[0].toLocalFile()))

    def closeEvent(self, evenement) -> None:  # noqa: N802
        if not self._confirmer_abandon():
            evenement.ignore()
            return
        self._parametres.setValue("geometrie", self.saveGeometry())
        self._parametres.setValue("etat", self.saveState())
        if self._document is not None:
            self._document.fermer()
        journal.info("Fermeture de MesurePlan")
        evenement.accept()

"""Panneau de style des annotations et dialogue d'export PDF."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QRadioButton, QSlider, QToolButton, QVBoxLayout,
                               QWidget)

from mesureplan import motifs
from mesureplan.annotations import STYLES_TRAIT, Style
from mesureplan.export_pdf import MODE_ANNOTATIONS, MODE_INCRUSTE

# Palette rapide : couleurs lisibles sur fond de plan blanc
PALETTE = ["#D81B60", "#E4572E", "#F39C12", "#2E9E4F", "#1F77D0", "#6A3D9A", "#2B2F36", "#FFD60A"]


def pastille(couleur: str | None, taille: int = 18) -> QIcon:
    """Icône carrée de la couleur donnée (damier pour « transparent »)."""
    pix = QPixmap(taille, taille)
    if couleur is None:
        pix.fill(QColor("white"))
        p = QPainter(pix)
        p.fillRect(0, 0, taille // 2, taille // 2, QColor("#CCCCCC"))
        p.fillRect(taille // 2, taille // 2, taille // 2, taille // 2, QColor("#CCCCCC"))
        p.end()
    else:
        pix.fill(QColor(couleur))
    return QIcon(pix)


class BoutonCouleur(QToolButton):
    """Bouton affichant une couleur ; clic → sélecteur de couleur."""

    couleur_changee = Signal(str)

    def __init__(self, couleur: str, titre: str, parent=None) -> None:
        super().__init__(parent)
        self._titre = titre
        self._couleur = couleur
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.clicked.connect(self._choisir)
        self.definir(couleur)

    @property
    def couleur(self) -> str:
        return self._couleur

    def definir(self, couleur: str) -> None:
        self._couleur = QColor(couleur).name().upper()
        self.setIcon(pastille(self._couleur))
        self.setText(self._couleur)

    def _choisir(self) -> None:
        choix = QColorDialog.getColor(QColor(self._couleur), self, self._titre)
        if choix.isValid():
            self.definir(choix.name())
            self.couleur_changee.emit(self._couleur)


class PanneauAnnotations(QWidget):
    """Réglages de style : appliqués au prochain tracé ET aux annotations sélectionnées."""

    style_change = Signal(object)        # Style
    orientation_saisie = Signal(float)   # angle (°) saisi pour l'annotation sélectionnée

    def __init__(self, style: Style, parent=None) -> None:
        super().__init__(parent)
        self._chargement = False

        # --- Trait
        groupe_trait = QGroupBox("Trait")
        self.bouton_trait = BoutonCouleur(style.couleur_trait, "Couleur du trait")
        self.bouton_trait.couleur_changee.connect(lambda _c: self._emettre())
        grille_palette = QGridLayout()
        grille_palette.setSpacing(3)
        for i, couleur in enumerate(PALETTE):
            bouton = QToolButton()
            bouton.setIcon(pastille(couleur, 16))
            bouton.setToolTip(f"{couleur} — clic : trait · Maj+clic : fond")
            bouton.setAutoRaise(True)
            bouton.clicked.connect(lambda _c=False, c=couleur: self._sur_palette(c))
            grille_palette.addWidget(bouton, 0, i)
        self.epaisseur = QDoubleSpinBox()
        self.epaisseur.setRange(0.1, 20.0)
        self.epaisseur.setSingleStep(0.25)
        self.epaisseur.setDecimals(2)
        self.epaisseur.setSuffix(" pt")
        self.epaisseur.valueChanged.connect(lambda _v: self._emettre())
        self.type_trait = QComboBox()
        self.type_trait.addItems(list(STYLES_TRAIT))
        self.type_trait.currentTextChanged.connect(lambda _t: self._emettre())
        self.double_fleche = QCheckBox("Flèche : pointe aux deux extrémités")
        self.double_fleche.toggled.connect(lambda _b: self._emettre())
        forme_trait = QFormLayout(groupe_trait)
        forme_trait.addRow("Couleur :", self.bouton_trait)
        forme_trait.addRow(grille_palette)
        forme_trait.addRow("Épaisseur :", self.epaisseur)
        forme_trait.addRow("Style :", self.type_trait)
        forme_trait.addRow(self.double_fleche)

        # --- Fond
        groupe_fond = QGroupBox("Fond")
        self.fond_transparent = QCheckBox("Transparent (pas de fond)")
        self.fond_transparent.toggled.connect(self._sur_transparence)
        self.bouton_fond = BoutonCouleur(style.couleur_fond or "#FFF59D", "Couleur du fond")
        self.bouton_fond.couleur_changee.connect(lambda _c: self._sur_couleur_fond())
        self.opacite = QSlider(Qt.Orientation.Horizontal)
        self.opacite.setRange(5, 100)
        self.label_opacite = QLabel()
        self.label_opacite.setMinimumWidth(40)
        self.opacite.valueChanged.connect(self._sur_opacite)
        ligne_opacite = QHBoxLayout()
        ligne_opacite.addWidget(self.opacite, 1)
        ligne_opacite.addWidget(self.label_opacite)
        forme_fond = QFormLayout(groupe_fond)
        forme_fond.addRow(self.fond_transparent)
        forme_fond.addRow("Couleur :", self.bouton_fond)
        forme_fond.addRow("Opacité :", ligne_opacite)

        # --- Texte
        groupe_texte = QGroupBox("Texte")
        self.taille_police = QDoubleSpinBox()
        self.taille_police.setRange(3.0, 144.0)
        self.taille_police.setSingleStep(1.0)
        self.taille_police.setDecimals(1)
        self.taille_police.setSuffix(" pt")
        self.taille_police.valueChanged.connect(lambda _v: self._emettre())
        self.cadre_texte = QCheckBox("Encadrer le texte")
        self.cadre_texte.toggled.connect(lambda _b: self._emettre())
        forme_texte = QFormLayout(groupe_texte)
        forme_texte.addRow("Taille :", self.taille_police)
        forme_texte.addRow(self.cadre_texte)

        # --- Motif de remplissage technique
        groupe_motif = QGroupBox("Motif de remplissage (rectangle, ovale, cercle, polygone)")
        self.combo_motif = QComboBox()
        for code, libelle in motifs.libelles():
            self.combo_motif.addItem(libelle, code)
        self.combo_motif.setMaxVisibleItems(26)
        self.combo_motif.currentIndexChanged.connect(self._sur_motif)
        self.motif_angle = QDoubleSpinBox()
        self.motif_angle.setRange(-180.0, 180.0)
        self.motif_angle.setSingleStep(15.0)
        self.motif_angle.setDecimals(1)
        self.motif_angle.setSuffix(" °")
        self.motif_angle.setWrapping(True)
        self.motif_angle.setToolTip("Rotation ajoutée à l'orientation propre du motif (ex. hachures à 45°)")
        self.motif_angle.valueChanged.connect(lambda _v: self._emettre())
        self.motif_echelle = QDoubleSpinBox()
        self.motif_echelle.setRange(0.1, 20.0)
        self.motif_echelle.setSingleStep(0.25)
        self.motif_echelle.setDecimals(2)
        self.motif_echelle.setPrefix("× ")
        self.motif_echelle.setToolTip("Multiplicateur de l'espacement du motif (1 = espacement de référence)")
        self.motif_echelle.valueChanged.connect(lambda _v: self._emettre())
        self.motif_epaisseur = QDoubleSpinBox()
        self.motif_epaisseur.setRange(0.05, 3.0)
        self.motif_epaisseur.setSingleStep(0.05)
        self.motif_epaisseur.setDecimals(2)
        self.motif_epaisseur.setSuffix(" pt")
        self.motif_epaisseur.valueChanged.connect(lambda _v: self._emettre())
        self.motif_couleur_trait = QCheckBox("Couleur du trait")
        self.motif_couleur_trait.toggled.connect(self._sur_couleur_motif_auto)
        self.bouton_motif = BoutonCouleur("#2B2F36", "Couleur du motif")
        self.bouton_motif.couleur_changee.connect(lambda _c: self._emettre())
        ligne_couleur_motif = QHBoxLayout()
        ligne_couleur_motif.addWidget(self.motif_couleur_trait)
        ligne_couleur_motif.addWidget(self.bouton_motif)
        forme_motif = QFormLayout(groupe_motif)
        forme_motif.addRow("Motif :", self.combo_motif)
        forme_motif.addRow("Angle :", self.motif_angle)
        forme_motif.addRow("Échelle :", self.motif_echelle)
        forme_motif.addRow("Épaisseur :", self.motif_epaisseur)
        forme_motif.addRow("Couleur :", ligne_couleur_motif)

        # --- Orientation de l'annotation sélectionnée
        groupe_orientation = QGroupBox("Orientation (rectangle, ovale, ligne, flèche sélectionnés)")
        self.orientation = QDoubleSpinBox()
        self.orientation.setRange(-180.0, 180.0)
        self.orientation.setDecimals(1)
        self.orientation.setSingleStep(5.0)
        self.orientation.setSuffix(" °")
        self.orientation.setWrapping(True)
        self.orientation.setKeyboardTracking(False)  # applique à la validation, pas à chaque chiffre
        self.orientation.setToolTip("Angle par rapport à l'horizontale, sens trigonométrique. "
                                    "À la souris : poignée ronde (Maj : pas de 15°).")
        self.orientation.valueChanged.connect(self._sur_orientation)
        ligne_orientation = QHBoxLayout()
        ligne_orientation.addWidget(self.orientation, 1)
        for libelle, increment in (("−90°", -90.0), ("+90°", 90.0), ("0°", None)):
            bouton = QPushButton(libelle)
            bouton.setMaximumWidth(52)
            bouton.clicked.connect(lambda _c=False, d=increment: self._sur_bouton_orientation(d))
            ligne_orientation.addWidget(bouton)
        disposition_orientation = QVBoxLayout(groupe_orientation)
        disposition_orientation.addLayout(ligne_orientation)
        self.groupe_orientation = groupe_orientation
        self.definir_orientation(None)

        aide = QLabel("<small>Les réglages s'appliquent au prochain tracé et aux annotations sélectionnées. "
                      "Outil Naviguer : glisser un élément le déplace (Maj : horizontal/vertical) ; glisser "
                      "une poignée carrée déplace un sommet, la poignée ronde fait tourner ; Ctrl+clic sur "
                      "une poignée supprime le sommet ; double-clic sur un côté ajoute un sommet.<br>"
                      "Épaisseurs et tailles en points « papier » (identiques dans le PDF exporté).</small>")
        aide.setWordWrap(True)

        disposition = QVBoxLayout(self)
        for widget in (groupe_trait, groupe_fond, groupe_motif, groupe_orientation, groupe_texte, aide):
            disposition.addWidget(widget)
        disposition.addStretch(1)
        self.charger(style)

    # --- Lecture / écriture du style ---------------------------------------------
    def style(self) -> Style:
        return Style(
            couleur_trait=self.bouton_trait.couleur,
            couleur_fond=None if self.fond_transparent.isChecked() else self.bouton_fond.couleur,
            opacite_fond=self.opacite.value() / 100.0,
            epaisseur=self.epaisseur.value(),
            trait=self.type_trait.currentText(),
            taille_police=self.taille_police.value(),
            cadre_texte=self.cadre_texte.isChecked(),
            double_fleche=self.double_fleche.isChecked(),
            motif=self.combo_motif.currentData() or "",
            motif_angle=self.motif_angle.value(),
            motif_echelle=self.motif_echelle.value(),
            motif_couleur=None if self.motif_couleur_trait.isChecked() else self.bouton_motif.couleur,
            motif_epaisseur=self.motif_epaisseur.value(),
        )

    def charger(self, style: Style) -> None:
        """Affiche un style (ex. celui de l'annotation sélectionnée) sans déclencher de modification."""
        self._chargement = True
        try:
            self.bouton_trait.definir(style.couleur_trait)
            self.fond_transparent.setChecked(style.couleur_fond is None)
            if style.couleur_fond:
                self.bouton_fond.definir(style.couleur_fond)
            self.bouton_fond.setEnabled(style.couleur_fond is not None)
            self.opacite.setEnabled(style.couleur_fond is not None)
            self.opacite.setValue(int(round(style.opacite_fond * 100)))
            self.label_opacite.setText(f"{self.opacite.value()} %")
            self.epaisseur.setValue(style.epaisseur)
            index = self.type_trait.findText(style.trait)
            self.type_trait.setCurrentIndex(max(index, 0))
            self.taille_police.setValue(style.taille_police)
            self.cadre_texte.setChecked(style.cadre_texte)
            self.double_fleche.setChecked(style.double_fleche)
            index = self.combo_motif.findData(style.motif or "")
            self.combo_motif.setCurrentIndex(max(index, 0))
            self.motif_angle.setValue(style.motif_angle)
            self.motif_echelle.setValue(style.motif_echelle)
            self.motif_epaisseur.setValue(style.motif_epaisseur)
            self.motif_couleur_trait.setChecked(style.motif_couleur is None)
            if style.motif_couleur:
                self.bouton_motif.definir(style.motif_couleur)
            self._activer_motif()
        finally:
            self._chargement = False

    def definir_orientation(self, angle: float | None) -> None:
        """Affiche l'orientation de l'annotation sélectionnée (None : non orientable / rien de sélectionné)."""
        self.orientation.blockSignals(True)
        self.orientation.setValue(angle or 0.0)
        self.orientation.blockSignals(False)
        self.groupe_orientation.setEnabled(angle is not None)

    def _sur_orientation(self, valeur: float) -> None:
        if self.groupe_orientation.isEnabled():
            self.orientation_saisie.emit(valeur)

    def _sur_bouton_orientation(self, increment: float | None) -> None:
        valeur = 0.0 if increment is None else self.orientation.value() + increment
        valeur = (valeur + 180.0) % 360.0 - 180.0
        self.orientation.setValue(valeur)  # émet orientation_saisie si la valeur change
        if increment is None:
            self._sur_orientation(valeur)

    def _activer_motif(self) -> None:
        actif = bool(self.combo_motif.currentData())
        for widget in (self.motif_angle, self.motif_echelle, self.motif_epaisseur, self.motif_couleur_trait):
            widget.setEnabled(actif)
        self.bouton_motif.setEnabled(actif and not self.motif_couleur_trait.isChecked())

    def _sur_motif(self, _index: int) -> None:
        self._activer_motif()
        self._emettre()

    def _sur_couleur_motif_auto(self, _auto: bool) -> None:
        self._activer_motif()
        self._emettre()

    # --- Réactions ---------------------------------------------------------------
    def _emettre(self) -> None:
        if not self._chargement:
            self.style_change.emit(self.style())

    def _sur_palette(self, couleur: str) -> None:
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.bouton_fond.definir(couleur)
            if self.fond_transparent.isChecked():
                self.fond_transparent.setChecked(False)  # émet via _sur_transparence
            else:
                self._emettre()
        else:
            self.bouton_trait.definir(couleur)
            self._emettre()

    def _sur_transparence(self, transparent: bool) -> None:
        self.bouton_fond.setEnabled(not transparent)
        self.opacite.setEnabled(not transparent)
        self._emettre()

    def _sur_couleur_fond(self) -> None:
        if self.fond_transparent.isChecked():
            self.fond_transparent.setChecked(False)  # choisir une couleur active le fond
        else:
            self._emettre()

    def _sur_opacite(self, valeur: int) -> None:
        self.label_opacite.setText(f"{valeur} %")
        self._emettre()


class DialogueExportPDF(QDialog):
    """Choix du fichier et des options d'export du PDF annoté."""

    def __init__(self, chemin_propose: Path, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Exporter un PDF annoté")
        self.setMinimumWidth(520)

        self.champ_chemin = QLineEdit(str(chemin_propose))
        parcourir = QPushButton("Parcourir…")
        parcourir.clicked.connect(self._parcourir)
        ligne_chemin = QHBoxLayout()
        ligne_chemin.addWidget(self.champ_chemin, 1)
        ligne_chemin.addWidget(parcourir)

        groupe_contenu = QGroupBox("Contenu ajouté au plan")
        self.case_annotations = QCheckBox("Annotations (flèches, formes, textes)")
        self.case_annotations.setChecked(True)
        self.case_mesures = QCheckBox("Mesures (traits et valeurs)")
        self.case_mesures.setChecked(True)
        self.case_references = QCheckBox("Cotes de référence de la calibration")
        disposition_contenu = QVBoxLayout(groupe_contenu)
        for case in (self.case_annotations, self.case_mesures, self.case_references):
            disposition_contenu.addWidget(case)

        groupe_mode = QGroupBox("Mode d'écriture")
        self.radio_incruste = QRadioButton("Incrusté dans le dessin — rendu identique partout, non modifiable")
        self.radio_annotations = QRadioButton("Annotations PDF — modifiables dans Okular, Acrobat, Xournal++…")
        self.radio_incruste.setChecked(True)
        disposition_mode = QVBoxLayout(groupe_mode)
        disposition_mode.addWidget(self.radio_incruste)
        disposition_mode.addWidget(self.radio_annotations)

        note = QLabel("<small>Le plan d'origine n'est jamais modifié : une copie est créée.</small>")
        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        boutons.button(QDialogButtonBox.StandardButton.Ok).setText("Exporter")
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        self.case_ouvrir = QCheckBox("Ouvrir le PDF après l'export")
        self.case_ouvrir.setChecked(True)

        disposition = QVBoxLayout(self)
        disposition.addWidget(QLabel("Fichier de sortie :"))
        disposition.addLayout(ligne_chemin)
        disposition.addWidget(groupe_contenu)
        disposition.addWidget(groupe_mode)
        disposition.addWidget(note)
        disposition.addWidget(self.case_ouvrir)
        disposition.addWidget(boutons)

    def _parcourir(self) -> None:
        chemin, _filtre = QFileDialog.getSaveFileName(self, "PDF annoté", self.champ_chemin.text(), "PDF (*.pdf)")
        if chemin:
            self.champ_chemin.setText(chemin if chemin.lower().endswith(".pdf") else chemin + ".pdf")

    @property
    def chemin(self) -> Path:
        return Path(self.champ_chemin.text().strip()).expanduser()

    @property
    def mode(self) -> str:
        return MODE_ANNOTATIONS if self.radio_annotations.isChecked() else MODE_INCRUSTE

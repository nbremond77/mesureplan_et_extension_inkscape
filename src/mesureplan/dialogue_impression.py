"""Dialogue « Imprimer à l'échelle » et impression directe via le système (Qt)."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QRectF, QSizeF, Qt
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QPainter
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton,
                               QVBoxLayout)

from mesureplan.echelle import lire_denominateur
from mesureplan.impression import (FORMATS_PAPIER, PT_PAR_MM, PlanImpression, facteur_agrandissement,
                                   planifier)
from mesureplan.impression_pdf import OptionsImpression
from mesureplan.mesures import formater_nombre

journal = logging.getLogger(__name__)
PERSONNALISE = "Personnalisé…"
SEUIL_FEUILLES = 30


class DialogueImpression(QDialog):
    """Paramètres de l'impression à l'échelle, avec résumé recalculé en direct."""

    def __init__(self, zones: dict[str, tuple[float, float, float, float]], metres_par_pt: float,
                 est_calibree: bool, denominateur_defaut: float, echelles_proposees: list[float],
                 chemin_propose: Path, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Imprimer à l'échelle")
        self.setMinimumWidth(560)
        self._zones = zones
        self._metres_par_pt = metres_par_pt
        self._est_calibree = est_calibree
        self.plan: PlanImpression | None = None
        self.action = ""

        # --- Échelle et papier
        self.combo_echelle = QComboBox()
        self.combo_echelle.setEditable(True)
        self.combo_echelle.addItems([f"1:{d:g}" for d in echelles_proposees])
        self.combo_echelle.setEditText(f"1:{denominateur_defaut:g}")
        self.combo_format = QComboBox()
        self.combo_format.addItems(list(FORMATS_PAPIER) + [PERSONNALISE])
        self.largeur_perso = self._spin_mm(50, 5000, 420)
        self.hauteur_perso = self._spin_mm(50, 5000, 297)
        ligne_perso = QHBoxLayout()
        ligne_perso.addWidget(self.largeur_perso)
        ligne_perso.addWidget(QLabel("×"))
        ligne_perso.addWidget(self.hauteur_perso)
        self.combo_orientation = QComboBox()
        self.combo_orientation.addItem("Automatique (moins de feuilles)", "auto")
        self.combo_orientation.addItem("Portrait", "portrait")
        self.combo_orientation.addItem("Paysage", "paysage")
        self.marge = self._spin_mm(3, 40, 10)
        self.recouvrement = self._spin_mm(0, 50, 10)
        self.recouvrement.setToolTip("Bande commune entre feuilles voisines, pour coller ou aligner la mosaïque")
        groupe_papier = QGroupBox("Échelle et papier")
        forme = QFormLayout(groupe_papier)
        forme.addRow("Échelle d'impression :", self.combo_echelle)
        forme.addRow("Format :", self.combo_format)
        forme.addRow("Format personnalisé :", ligne_perso)
        forme.addRow("Orientation :", self.combo_orientation)
        forme.addRow("Marges :", self.marge)
        forme.addRow("Recouvrement (mosaïque) :", self.recouvrement)

        # --- Zone
        groupe_zone = QGroupBox("Zone à imprimer")
        self.radio_page = QRadioButton("Page entière")
        self.radio_vue = QRadioButton("Zone affichée à l'écran (cadrez-la avant d'ouvrir ce dialogue)")
        self.radio_page.setChecked(True)
        self._groupe_zone = QButtonGroup(self)
        self._groupe_zone.addButton(self.radio_page)
        self._groupe_zone.addButton(self.radio_vue)
        disposition_zone = QVBoxLayout(groupe_zone)
        disposition_zone.addWidget(self.radio_page)
        disposition_zone.addWidget(self.radio_vue)

        # --- Contenu et repères
        groupe_contenu = QGroupBox("Contenu et repères")
        self.case_annotations = QCheckBox("Annotations")
        self.case_mesures = QCheckBox("Mesures")
        self.case_barre = QCheckBox("Barre d'échelle graduée")
        self.case_controle = QCheckBox("Segment de contrôle de 100 mm")
        self.case_reperes = QCheckBox("Repères d'angle et lignes de recouvrement")
        self.case_assemblage = QCheckBox("Page « plan d'assemblage » (mosaïque)")
        for case in (self.case_annotations, self.case_mesures, self.case_barre, self.case_controle,
                     self.case_reperes, self.case_assemblage):
            case.setChecked(True)
        disposition_contenu = QFormLayout(groupe_contenu)
        disposition_contenu.addRow(self.case_annotations, self.case_mesures)
        disposition_contenu.addRow(self.case_barre, self.case_controle)
        disposition_contenu.addRow(self.case_reperes, self.case_assemblage)

        # --- Résumé
        self.label_resume = QLabel()
        self.label_resume.setWordWrap(True)
        self.label_resume.setTextFormat(Qt.TextFormat.RichText)
        self.label_resume.setStyleSheet("QLabel { background: #F4F6F8; border: 1px solid #D0D5DB;"
                                        " border-radius: 4px; padding: 8px; }")

        # --- Fichier et boutons
        self.champ_chemin = QLineEdit(str(chemin_propose))
        bouton_parcourir = QPushButton("Parcourir…")
        bouton_parcourir.clicked.connect(self._parcourir)
        ligne_fichier = QHBoxLayout()
        ligne_fichier.addWidget(QLabel("PDF d'impression :"))
        ligne_fichier.addWidget(self.champ_chemin, 1)
        ligne_fichier.addWidget(bouton_parcourir)
        self.case_ouvrir = QCheckBox("Ouvrir le PDF créé")
        self.case_ouvrir.setChecked(True)
        self.bouton_pdf = QPushButton("Créer le PDF")
        self.bouton_pdf.setDefault(True)
        self.bouton_pdf.setToolTip("Méthode recommandée : PDF vectoriel, à imprimer à 100 % depuis votre visionneuse")
        self.bouton_imprimer = QPushButton("Imprimer…")
        self.bouton_imprimer.setToolTip("Envoi direct à une imprimante (rendu 300 dpi)")
        bouton_annuler = QPushButton("Annuler")
        self.bouton_pdf.clicked.connect(lambda: self._valider("pdf"))
        self.bouton_imprimer.clicked.connect(lambda: self._valider("imprimer"))
        bouton_annuler.clicked.connect(self.reject)
        ligne_boutons = QHBoxLayout()
        ligne_boutons.addWidget(self.case_ouvrir)
        ligne_boutons.addStretch(1)
        for bouton in (self.bouton_imprimer, self.bouton_pdf, bouton_annuler):
            ligne_boutons.addWidget(bouton)

        disposition = QVBoxLayout(self)
        for widget in (groupe_papier, groupe_zone, groupe_contenu, self.label_resume):
            disposition.addWidget(widget)
        disposition.addLayout(ligne_fichier)
        disposition.addLayout(ligne_boutons)

        # Recalcul à chaque changement
        self.combo_echelle.currentTextChanged.connect(self._recalculer)
        self.combo_format.currentTextChanged.connect(self._recalculer)
        self.combo_orientation.currentIndexChanged.connect(self._recalculer)
        for spin in (self.largeur_perso, self.hauteur_perso, self.marge, self.recouvrement):
            spin.valueChanged.connect(self._recalculer)
        self.radio_page.toggled.connect(self._recalculer)
        self._recalculer()

    @staticmethod
    def _spin_mm(minimum: float, maximum: float, valeur: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(0)
        spin.setSuffix(" mm")
        spin.setValue(valeur)
        return spin

    # ------------------------------------------------------------------
    @property
    def zone(self) -> tuple[float, float, float, float]:
        return self._zones["vue" if self.radio_vue.isChecked() else "page"]

    @property
    def options(self) -> OptionsImpression:
        return OptionsImpression(barre_echelle=self.case_barre.isChecked(),
                                 segment_controle=self.case_controle.isChecked(),
                                 reperes_assemblage=self.case_reperes.isChecked(),
                                 plan_assemblage=self.case_assemblage.isChecked())

    @property
    def chemin(self) -> Path:
        return Path(self.champ_chemin.text().strip()).expanduser()

    def _format(self) -> tuple[str, tuple[float, float]]:
        nom = self.combo_format.currentText()
        perso = nom == PERSONNALISE
        self.largeur_perso.setEnabled(perso)
        self.hauteur_perso.setEnabled(perso)
        if perso:
            l, h = self.largeur_perso.value(), self.hauteur_perso.value()
            return f"{l:g}×{h:g} mm", (l, h)
        return nom, FORMATS_PAPIER[nom]

    def _recalculer(self, *_args) -> None:
        """Calcule la mise en page et met à jour le résumé (ou affiche l'erreur)."""
        try:
            denominateur = lire_denominateur(self.combo_echelle.currentText())
            nom_format, format_mm = self._format()
            k = facteur_agrandissement(self._metres_par_pt, denominateur)
            self.plan = planifier(self.zone, k, format_mm, nom_format, self.combo_orientation.currentData(),
                                  self.marge.value(), self.recouvrement.value(), denominateur=denominateur)
        except ValueError as erreur:
            self.plan = None
            self.label_resume.setText(f"<span style='color:#C0392B'><b>Impossible :</b> {erreur}</span>")
            self.bouton_pdf.setEnabled(False)
            self.bouton_imprimer.setEnabled(False)
            return

        plan = self.plan
        x0, y0, x1, y1 = plan.zone
        reel_l, reel_h = (x1 - x0) * self._metres_par_pt, (y1 - y0) * self._metres_par_pt
        papier_l, papier_h = plan.taille_imprimee_mm
        lignes = [
            f"Zone réelle : <b>{formater_nombre(reel_l, 2)} × {formater_nombre(reel_h, 2)} m</b> → "
            f"imprimée : <b>{formater_nombre(papier_l, 0)} × {formater_nombre(papier_h, 0)} mm</b> "
            f"(agrandissement ×{formater_nombre(plan.k, 3)} par rapport au PDF)",
        ]
        if plan.nombre_feuilles == 1:
            lignes.append(f"<b>1 feuille {plan.format} {plan.orientation}</b>")
        else:
            assemblage = " + plan d'assemblage" if self.case_assemblage.isChecked() else ""
            lignes.append(f"<b>{plan.nombre_feuilles} feuilles {plan.format} {plan.orientation}</b> "
                          f"({plan.lignes} ligne(s) × {plan.colonnes} colonne(s)){assemblage}")
        if not self._est_calibree:
            lignes.append("<span style='color:#C77700'>⚠ Échelle de la page non vérifiée par calibration : "
                          "si le cartouche est faux, l'impression le sera aussi.</span>")
        if plan.nombre_feuilles > SEUIL_FEUILLES:
            lignes.append("<span style='color:#C0392B'>⚠ Beaucoup de feuilles : choisissez un format plus grand "
                          "(reprographie) ou une échelle plus petite.</span>")
        lignes.append("<small>À l'impression : taille réelle / 100 %, jamais « ajuster à la page ». "
                      "Vérifiez le segment de contrôle de 100 mm avec une règle.</small>")
        self.label_resume.setText("<br>".join(lignes))
        self.bouton_pdf.setEnabled(True)
        self.bouton_imprimer.setEnabled(True)

    def _parcourir(self) -> None:
        chemin, _filtre = QFileDialog.getSaveFileName(self, "PDF d'impression", self.champ_chemin.text(),
                                                      "PDF (*.pdf)")
        if chemin:
            self.champ_chemin.setText(chemin if chemin.lower().endswith(".pdf") else chemin + ".pdf")

    def _valider(self, action: str) -> None:
        if self.plan is not None:
            self.action = action
            self.accept()


def imprimer_pdf(parent, chemin_pdf: Path, plan: PlanImpression, nom_document: str) -> bool:
    """Envoie le PDF d'impression à une imprimante, à taille réelle (rendu raster 300 dpi).

    Le format de papier est imposé ; le pilote doit être réglé sans mise à l'échelle.
    Retourne False si l'utilisateur annule.
    """
    import pymupdf

    largeur_mm = plan.largeur_feuille / PT_PAR_MM
    hauteur_mm = plan.hauteur_feuille / PT_PAR_MM
    imprimante = QPrinter(QPrinter.PrinterMode.HighResolution)
    imprimante.setDocName(nom_document)
    # Taille de page toujours décrite en portrait, orientation à part
    taille = QPageSize(QSizeF(min(largeur_mm, hauteur_mm), max(largeur_mm, hauteur_mm)),
                       QPageSize.Unit.Millimeter, plan.format, QPageSize.SizeMatchPolicy.FuzzyMatch)
    imprimante.setPageSize(taille)
    imprimante.setPageOrientation(QPageLayout.Orientation.Landscape if largeur_mm > hauteur_mm
                                  else QPageLayout.Orientation.Portrait)
    imprimante.setFullPage(True)  # origine au bord du papier : nos marges sont déjà dans le dessin
    dialogue = QPrintDialog(imprimante, parent)
    dialogue.setWindowTitle(f"Imprimer à l'échelle 1:{plan.denominateur:g} — {plan.format} {plan.orientation}")
    if not dialogue.exec():
        return False

    resolution = imprimante.resolution()
    dpi = min(resolution, 300)
    peintre = QPainter()
    document = pymupdf.open(chemin_pdf)
    try:
        if not peintre.begin(imprimante):
            raise RuntimeError("Impossible de démarrer l'impression (imprimante indisponible ?)")
        for indice, page in enumerate(document):
            if indice:
                imprimante.newPage()
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
            # Dimension cible en pixels imprimante calculée depuis la taille physique de la page
            cible = QRectF(0, 0, page.rect.width / 72.0 * resolution, page.rect.height / 72.0 * resolution)
            peintre.drawImage(cible, image)
        journal.info("Impression envoyée : %d page(s), %g dpi", document.page_count, dpi)
    finally:
        if peintre.isActive():
            peintre.end()
        document.close()
    return True

"""Panneaux latéraux : échelle/calibration et liste des mesures."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFormLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from mesureplan.echelle import METRES_PAR_POINT, DetectionEchelle, EchellePage
from mesureplan.mesures import Formateur, Mesure, TypeMesure, formater_nombre


def _texte_echelle(denominateur: float) -> str:
    """100 → « 1:100 », 98.66 → « 1:98,66 »."""
    if abs(denominateur - round(denominateur)) < 1e-6:
        return f"1:{int(round(denominateur))}"
    return "1:" + formater_nombre(denominateur, 2)


class PanneauEchelle(QWidget):
    """Échelle du cartouche, cotes de référence et synthèse de cohérence."""

    denominateur_saisi = Signal(str)
    demande_calibration = Signal()
    supprimer_reference = Signal(int)
    effacer_references = Signal()
    appliquer_detection = Signal()

    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        cfg = config["echelle"]
        self._seuil_ecart = float(cfg.get("seuil_alerte_ecart_pct", 2.0))
        self._seuil_dispersion = float(cfg.get("seuil_alerte_dispersion_pct", 1.0))

        # --- Cartouche
        groupe_cartouche = QGroupBox("Échelle du cartouche")
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo.addItems([_texte_echelle(d) for d in cfg.get("echelles_proposees", [100])])
        self.combo.setToolTip("Saisir 1:100, 1/100 ou 100 puis Entrée")
        self.combo.activated.connect(lambda _i: self.denominateur_saisi.emit(self.combo.currentText()))
        self.combo.lineEdit().returnPressed.connect(lambda: self.denominateur_saisi.emit(self.combo.currentText()))
        self.label_detection = QLabel()
        self.label_detection.setWordWrap(True)
        self.bouton_detection = QPushButton("Appliquer l'échelle lue")
        self.bouton_detection.clicked.connect(self.appliquer_detection)
        forme = QFormLayout()
        forme.addRow("Échelle :", self.combo)
        disposition_cartouche = QVBoxLayout(groupe_cartouche)
        disposition_cartouche.addLayout(forme)
        disposition_cartouche.addWidget(self.label_detection)
        disposition_cartouche.addWidget(self.bouton_detection)

        # --- Calibration
        groupe_calibration = QGroupBox("Calibration sur cotes connues")
        self.bouton_calibrer = QPushButton("Tracer une cote de référence  (C)")
        self.bouton_calibrer.setToolTip("Cliquer les deux extrémités d'une cote écrite sur le plan, "
                                        "puis saisir sa valeur réelle. Plusieurs cotes = contrôle de cohérence.")
        self.bouton_calibrer.clicked.connect(self.demande_calibration)
        self.table_references = QTableWidget(0, 3)
        self.table_references.setHorizontalHeaderLabels(["Cote réelle", "Au cartouche", "Échelle déduite"])
        self.table_references.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_references.verticalHeader().setVisible(False)
        self.table_references.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_references.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_references.setMaximumHeight(130)
        bouton_supprimer = QPushButton("Supprimer")
        bouton_supprimer.clicked.connect(self._supprimer_selection)
        bouton_effacer = QPushButton("Revenir au cartouche")
        bouton_effacer.clicked.connect(self.effacer_references)
        ligne_boutons = QHBoxLayout()
        ligne_boutons.addWidget(bouton_supprimer)
        ligne_boutons.addWidget(bouton_effacer)
        disposition_calibration = QVBoxLayout(groupe_calibration)
        disposition_calibration.addWidget(self.bouton_calibrer)
        disposition_calibration.addWidget(self.table_references)
        disposition_calibration.addLayout(ligne_boutons)

        # --- Synthèse
        self.label_synthese = QLabel()
        self.label_synthese.setWordWrap(True)
        self.label_synthese.setTextFormat(Qt.TextFormat.RichText)
        self.label_synthese.setStyleSheet("QLabel { background: #F4F6F8; border: 1px solid #D0D5DB;"
                                          " border-radius: 4px; padding: 6px; }")

        disposition = QVBoxLayout(self)
        disposition.addWidget(groupe_cartouche)
        disposition.addWidget(groupe_calibration)
        disposition.addWidget(self.label_synthese)
        disposition.addStretch(1)

    def _supprimer_selection(self) -> None:
        ligne = self.table_references.currentRow()
        if ligne >= 0:
            self.supprimer_reference.emit(ligne)

    def actualiser(self, echelle: EchellePage, detection: DetectionEchelle | None, formateur: Formateur) -> None:
        """Met à jour tous les champs à partir de l'échelle de la page courante."""
        self.combo.blockSignals(True)
        self.combo.setEditText(_texte_echelle(echelle.denominateur_cartouche))
        self.combo.blockSignals(False)

        if detection is None:
            self.label_detection.setText("<i>Aucune échelle lisible dans le texte du plan.</i>")
            self.bouton_detection.setEnabled(False)
        else:
            confirmation = "précédée de « Éch. »" if detection.confirmee_par_mot_cle else "sans mot-clé"
            autres = ", ".join(_texte_echelle(d) for d in detection.autres)
            texte = (f"Lue sur le plan : <b>{_texte_echelle(detection.denominateur)}</b> "
                     f"({detection.occurrences}×, {confirmation})")
            if autres:
                texte += f"<br>Autres échelles présentes : {autres} (détails ?)"
            self.label_detection.setText(texte)
            self.bouton_detection.setEnabled(abs(detection.denominateur - echelle.denominateur_cartouche) > 1e-9)

        self.table_references.setRowCount(len(echelle.references))
        for ligne, ref in enumerate(echelle.references):
            au_cartouche = ref.longueur_pt * echelle.facteur_cartouche
            valeurs = [formateur.longueur(ref.longueur_reelle_m), formateur.longueur(au_cartouche),
                       _texte_echelle(ref.facteur / METRES_PAR_POINT)]
            for colonne, texte in enumerate(valeurs):
                item = QTableWidgetItem(texte)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table_references.setItem(ligne, colonne, item)

        # Synthèse avec alertes colorées
        lignes = [f"Échelle appliquée : <b>{_texte_echelle(echelle.denominateur_effectif)}</b>",
                  f"Source : {echelle.libelle_source}"]
        ecart = echelle.ecart_cartouche_pct
        if ecart is not None:
            couleur = "#C0392B" if abs(ecart) > self._seuil_ecart else "#2E7D32"
            lignes.append(f"Écart / cartouche : <b style='color:{couleur}'>{formater_nombre(ecart, 2)} %</b>")
            if abs(ecart) > self._seuil_ecart:
                lignes.append("<span style='color:#C0392B'>Plan probablement imprimé ou exporté hors échelle "
                              "(« ajusté à la page ») : la calibration est indispensable.</span>")
        dispersion = echelle.dispersion_pct
        if dispersion is not None:
            couleur = "#C0392B" if dispersion > self._seuil_dispersion else "#2E7D32"
            lignes.append(f"Cohérence des cotes : <b style='color:{couleur}'>{formater_nombre(dispersion, 2)} %</b>"
                          " d'écart max")
            if dispersion > self._seuil_dispersion:
                lignes.append("<span style='color:#C0392B'>Références incohérentes : cote mal pointée, "
                              "mauvaise saisie, ou plan déformé (échelles X/Y différentes).</span>")
        elif echelle.est_calibree:
            lignes.append("<i>Conseil : ajoutez une 2<sup>e</sup> cote, idéalement perpendiculaire, "
                          "pour contrôler la cohérence.</i>")
        else:
            lignes.append("<i>Échelle non vérifiée : tracez au moins une cote de référence.</i>")
        self.label_synthese.setText("<br>".join(lignes))


class PanneauMesures(QWidget):
    """Tableau des mesures de la page, totaux et actions."""

    selection_changee = Signal(object)    # set[int]
    renommage = Signal(int, str)
    suppression = Signal(object)          # set[int]
    cadrage = Signal(int)
    unite_changee = Signal(str)
    export_demande = Signal()

    COLONNES = ["Nom", "Type", "Valeur", "Détail"]

    def __init__(self, formateur: Formateur, parent=None) -> None:
        super().__init__(parent)
        self._maj_en_cours = False
        self._identifiants: list[int] = []

        self.combo_unite = QComboBox()
        self.combo_unite.addItems(["m", "cm", "mm"])
        self.combo_unite.setCurrentText(formateur.unite_longueur)
        self.combo_unite.currentTextChanged.connect(self.unite_changee)
        ligne_unite = QHBoxLayout()
        ligne_unite.addWidget(QLabel("Unité des longueurs :"))
        ligne_unite.addWidget(self.combo_unite)
        ligne_unite.addStretch(1)

        self.table = QTableWidget(0, len(self.COLONNES))
        self.table.setHorizontalHeaderLabels(self.COLONNES)
        entete = self.table.horizontalHeader()
        entete.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for colonne in range(1, len(self.COLONNES)):
            entete.setSectionResizeMode(colonne, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.EditKeyPressed
                                   | QAbstractItemView.EditTrigger.SelectedClicked)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self._sur_selection)
        self.table.itemChanged.connect(self._sur_modification)
        self.table.cellDoubleClicked.connect(self._sur_double_clic)

        self.label_totaux = QLabel()
        self.label_totaux.setWordWrap(True)
        self.label_totaux.setTextFormat(Qt.TextFormat.RichText)

        bouton_supprimer = QPushButton("Supprimer")
        bouton_supprimer.clicked.connect(lambda: self.suppression.emit(self.selection()))
        bouton_export = QPushButton("Exporter CSV…")
        bouton_export.clicked.connect(self.export_demande)
        ligne_boutons = QHBoxLayout()
        ligne_boutons.addWidget(bouton_supprimer)
        ligne_boutons.addStretch(1)
        ligne_boutons.addWidget(bouton_export)

        disposition = QVBoxLayout(self)
        disposition.addLayout(ligne_unite)
        disposition.addWidget(self.table, 1)
        disposition.addWidget(self.label_totaux)
        disposition.addLayout(ligne_boutons)

    def selection(self) -> set[int]:
        lignes = {index.row() for index in self.table.selectionModel().selectedRows()}
        return {self._identifiants[ligne] for ligne in lignes if ligne < len(self._identifiants)}

    def selectionner(self, identifiants: set[int]) -> None:
        """Sélection pilotée depuis le plan."""
        self.table.blockSignals(True)
        self.table.clearSelection()
        for ligne, identifiant in enumerate(self._identifiants):
            if identifiant in identifiants:
                self.table.selectRow(ligne)
                self.table.scrollToItem(self.table.item(ligne, 0))
        self.table.blockSignals(False)

    def _sur_selection(self) -> None:
        if not self._maj_en_cours:
            self.selection_changee.emit(self.selection())

    def _sur_modification(self, item: QTableWidgetItem) -> None:
        if self._maj_en_cours or item.column() != 0:
            return
        ligne = item.row()
        if ligne < len(self._identifiants):
            self.renommage.emit(self._identifiants[ligne], item.text().strip())

    def _sur_double_clic(self, ligne: int, colonne: int) -> None:
        if colonne != 0 and ligne < len(self._identifiants):
            self.cadrage.emit(self._identifiants[ligne])

    def actualiser(self, mesures: list[Mesure], echelle: EchellePage, formateur: Formateur,
                   selection: set[int]) -> None:
        """Remplit la table et calcule les totaux (sélection, sinon toute la page)."""
        self._maj_en_cours = True
        self.table.clearSelection()
        self._identifiants = [m.identifiant for m in mesures]
        self.table.setRowCount(len(mesures))
        for ligne, m in enumerate(mesures):
            perimetre = formateur.detail(m, echelle)  # périmètre, ou ΔX / ΔY / angle
            valeur = formateur.valeur_principale(m, echelle)
            if m.avertissement:
                valeur = "⚠ " + valeur
            cellules = [m.nom, m.type.value, valeur, perimetre]
            for colonne, texte in enumerate(cellules):
                item = QTableWidgetItem(texte)
                if colonne != 0:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if colonne >= 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if m.avertissement:
                    item.setToolTip(m.avertissement)
                self.table.setItem(ligne, colonne, item)
            if m.identifiant in selection:
                self.table.selectRow(ligne)
        self._maj_en_cours = False

        # Totaux par type
        concernees = [m for m in mesures if m.identifiant in selection] or mesures
        portee = "sélection" if len(concernees) != len(mesures) else "page"
        surfaces = [m.valeurs(echelle)["surface"] for m in concernees if m.type is TypeMesure.SURFACE]
        longueurs = [m.valeurs(echelle)["longueur"] for m in concernees
                     if m.type in (TypeMesure.DISTANCE, TypeMesure.DISTANCE_XY, TypeMesure.CHAINE)]
        morceaux = []
        if surfaces:
            morceaux.append(f"Σ surfaces : <b>{formateur.surface(sum(surfaces))}</b> ({len(surfaces)})")
        if longueurs:
            morceaux.append(f"Σ longueurs : <b>{formateur.longueur(sum(longueurs))}</b> ({len(longueurs)})")
        self.label_totaux.setText(f"Totaux ({portee}) — " + " · ".join(morceaux) if morceaux
                                  else "<i>Aucune mesure sur cette page.</i>")

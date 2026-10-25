"""Mise en place de la journalisation (console + fichier tournant).

Chaque enregistrement reçoit le nom de l'utilisateur système via un filtre,
afin de tracer qui a produit quelles mesures sur un poste partagé.
"""

from __future__ import annotations

import getpass
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Format commun : horodatage | niveau | utilisateur | module | message
FORMAT_JOURNAL = "%(asctime)s | %(levelname)-8s | %(utilisateur)s | %(module)s | %(message)s"
FORMAT_DATE = "%Y-%m-%d %H:%M:%S"


class FiltreUtilisateur(logging.Filter):
    """Injecte l'identifiant de l'utilisateur courant dans chaque enregistrement."""

    def __init__(self) -> None:
        super().__init__()
        try:
            # getpass.getuser() lit les variables d'environnement puis la base des comptes
            self._utilisateur = getpass.getuser()
        except Exception:  # noqa: BLE001 — environnement exotique : on ne bloque pas l'appli
            self._utilisateur = "inconnu"

    def filter(self, record: logging.LogRecord) -> bool:
        # Ajout de l'attribut utilisé dans FORMAT_JOURNAL
        record.utilisateur = self._utilisateur
        return True


def configurer_journalisation(cfg: dict, dossier_base: Path) -> Path:
    """Configure le journal racine à partir de la section « journalisation » du JSON.

    Retourne le chemin du fichier journal effectivement utilisé.
    """
    # Niveau lu dans la configuration, INFO par défaut si la valeur est invalide
    niveau = getattr(logging, str(cfg.get("niveau", "INFO")).upper(), logging.INFO)

    # Chemin du fichier : relatif au dossier de base de la configuration
    fichier = Path(cfg.get("fichier", "logs/mesureplan.log")).expanduser()
    if not fichier.is_absolute():
        fichier = dossier_base / fichier
    fichier.parent.mkdir(parents=True, exist_ok=True)

    racine = logging.getLogger()
    racine.setLevel(niveau)
    # On repart d'une configuration propre (utile si appelée deux fois)
    for gestionnaire in list(racine.handlers):
        racine.removeHandler(gestionnaire)

    formateur = logging.Formatter(FORMAT_JOURNAL, FORMAT_DATE)
    filtre = FiltreUtilisateur()

    # Sortie console
    console = logging.StreamHandler()
    # Fichier tournant : taille maximale et nombre d'archives configurables
    fichier_tournant = RotatingFileHandler(
        fichier,
        maxBytes=int(cfg.get("taille_max_octets", 1_048_576)),
        backupCount=int(cfg.get("nombre_sauvegardes", 5)),
        encoding="utf-8",
    )
    for gestionnaire in (console, fichier_tournant):
        gestionnaire.setFormatter(formateur)
        # Filtre posé sur le gestionnaire : couvre aussi les journaux des bibliothèques
        gestionnaire.addFilter(filtre)
        racine.addHandler(gestionnaire)

    return fichier

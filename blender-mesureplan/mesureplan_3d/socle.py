"""Configuration JSON et journalisation de l'extension (conventions du projet MesurePlan).

- Configuration : config_defaut.json (embarqué, en lecture seule) fusionné avec
  config.json du dossier utilisateur de l'extension, créé au premier lancement.
- Journal : console + fichier tournant dans le dossier utilisateur, format
  horodatage | niveau | utilisateur | module | message, niveau lu dans le JSON.
Une extension Blender ne doit jamais écrire dans son propre dossier : tout ce qui
est écrit va dans bpy.utils.extension_path_user (Blender ≥ 4.2), sinon dans
~/.mesureplan_3d (installation « addon » historique).
"""

from __future__ import annotations

import copy
import getpass
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

NOM_JOURNAL = "mesureplan_3d"
journal = logging.getLogger(NOM_JOURNAL)
_CONFIG: dict | None = None


def dossier_utilisateur(package: str, sous_dossier: str) -> Path:
    """Dossier inscriptible propre à l'extension."""
    try:
        import bpy

        if hasattr(bpy.utils, "extension_path_user") and package.startswith("bl_ext."):
            return Path(bpy.utils.extension_path_user(package, path=sous_dossier, create=True))
    except Exception:  # noqa: BLE001 — hors Blender ou API absente : repli
        pass
    dossier = Path.home() / ".mesureplan_3d" / sous_dossier
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier


def _fusionner(defaut: dict, utilisateur: dict) -> dict:
    """Fusion récursive : l'utilisateur surcharge, les clés absentes viennent du défaut."""
    resultat = copy.deepcopy(defaut)
    for cle, valeur in utilisateur.items():
        if isinstance(valeur, dict) and isinstance(resultat.get(cle), dict):
            resultat[cle] = _fusionner(resultat[cle], valeur)
        else:
            resultat[cle] = valeur
    return resultat


def charger_configuration(package: str) -> dict:
    """Configuration effective (mise en cache)."""
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG
    texte_defaut = (Path(__file__).parent / "config_defaut.json").read_text(encoding="utf-8")
    defaut = json.loads(texte_defaut)
    try:
        chemin = dossier_utilisateur(package, "config") / "config.json"
        if not chemin.exists():
            # Copie modifiable par l'utilisateur
            chemin.write_text(texte_defaut, encoding="utf-8")
        _CONFIG = _fusionner(defaut, json.loads(chemin.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        _CONFIG = defaut
    return _CONFIG


class FiltreUtilisateur(logging.Filter):
    """Injecte l'utilisateur système dans chaque enregistrement."""

    def __init__(self) -> None:
        super().__init__()
        try:
            self.utilisateur = getpass.getuser()
        except Exception:  # noqa: BLE001
            self.utilisateur = "inconnu"

    def filter(self, record: logging.LogRecord) -> bool:
        record.utilisateur = self.utilisateur
        return True


def configurer_journal(package: str, cfg: dict) -> None:
    """Console + fichier tournant ; idempotent (rechargement de l'extension)."""
    for gestionnaire in list(journal.handlers):
        journal.removeHandler(gestionnaire)
        gestionnaire.close()
    journal.setLevel(getattr(logging, str(cfg.get("niveau", "INFO")).upper(), logging.INFO))
    journal.propagate = False
    format_ = logging.Formatter("%(asctime)s | %(levelname)-8s | %(utilisateur)s | %(module)s | %(message)s",
                                "%Y-%m-%d %H:%M:%S")
    filtre = FiltreUtilisateur()
    gestionnaires: list[logging.Handler] = [logging.StreamHandler()]
    try:
        fichier = dossier_utilisateur(package, "logs") / "mesureplan_3d.log"
        gestionnaires.append(RotatingFileHandler(fichier, maxBytes=int(cfg.get("taille_max_octets", 524288)),
                                                 backupCount=int(cfg.get("nombre_sauvegardes", 3)),
                                                 encoding="utf-8"))
    except OSError:
        pass  # journal console seulement
    for g in gestionnaires:
        g.setFormatter(format_)
        g.addFilter(filtre)
        journal.addHandler(g)


def fermer_journal() -> None:
    for gestionnaire in list(journal.handlers):
        journal.removeHandler(gestionnaire)
        gestionnaire.close()

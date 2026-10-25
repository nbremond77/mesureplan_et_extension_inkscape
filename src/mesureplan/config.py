"""Chargement de la configuration applicative JSON.

Ordre de recherche :
  1. variable d'environnement MESUREPLAN_CONFIG (chemin d'un fichier JSON) ;
  2. ./config/config.json (lancement depuis le dossier du projet) ;
  3. ~/.mesureplan/config/config.json (installation utilisateur).
À défaut, la configuration embarquée est copiée en 3. pour être personnalisée.
Les clés absentes du fichier utilisateur sont complétées par les valeurs par défaut.
"""

from __future__ import annotations

import copy
import json
import os
from importlib import resources
from pathlib import Path

NOM_VARIABLE_ENV = "MESUREPLAN_CONFIG"
DOSSIER_UTILISATEUR = Path.home() / ".mesureplan"


def _texte_config_defaut() -> str:
    """Lit le JSON embarqué dans le paquet."""
    return resources.files("mesureplan").joinpath("config_defaut.json").read_text(encoding="utf-8")


def fusionner(defaut: dict, utilisateur: dict) -> dict:
    """Fusion récursive : l'utilisateur surcharge, les clés manquantes viennent du défaut."""
    resultat = copy.deepcopy(defaut)
    for cle, valeur in utilisateur.items():
        if isinstance(valeur, dict) and isinstance(resultat.get(cle), dict):
            resultat[cle] = fusionner(resultat[cle], valeur)
        else:
            resultat[cle] = valeur
    return resultat


def charger_configuration() -> tuple[dict, Path, str]:
    """Retourne (configuration, dossier de base, message d'origine).

    Le dossier de base sert à résoudre les chemins relatifs (journaux) :
    c'est le parent du dossier « config ».
    Aucune journalisation ici : elle n'est pas encore configurée.
    """
    defaut = json.loads(_texte_config_defaut())

    candidats: list[Path] = []
    if os.environ.get(NOM_VARIABLE_ENV):
        candidats.append(Path(os.environ[NOM_VARIABLE_ENV]).expanduser())
    candidats.append(Path.cwd() / "config" / "config.json")
    candidats.append(DOSSIER_UTILISATEUR / "config" / "config.json")

    for chemin in candidats:
        if chemin.is_file():
            with chemin.open(encoding="utf-8") as flux:
                utilisateur = json.load(flux)
            return fusionner(defaut, utilisateur), chemin.resolve().parent.parent, f"Configuration lue : {chemin}"

    # Première exécution : on dépose une copie modifiable de la configuration
    cible = DOSSIER_UTILISATEUR / "config" / "config.json"
    message = f"Configuration par défaut utilisée et copiée vers {cible}"
    try:
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(_texte_config_defaut(), encoding="utf-8")
    except OSError as erreur:
        message = f"Configuration par défaut utilisée (copie impossible : {erreur})"
    return defaut, DOSSIER_UTILISATEUR, message

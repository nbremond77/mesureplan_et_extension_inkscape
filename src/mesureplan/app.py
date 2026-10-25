"""Point d'entrée de l'application MesurePlan."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from mesureplan import __version__
from mesureplan.config import charger_configuration
from mesureplan.journalisation import configurer_journalisation

journal = logging.getLogger(__name__)


def _journaliser_exception_non_geree(type_exc, valeur, trace) -> None:
    """Toute exception non interceptée (y compris dans un slot Qt) part au journal."""
    if issubclass(type_exc, KeyboardInterrupt):
        sys.__excepthook__(type_exc, valeur, trace)
        return
    journal.critical("Exception non gérée", exc_info=(type_exc, valeur, trace))


def main() -> None:
    # 1. Configuration puis journalisation (dans cet ordre : le journal dépend du JSON)
    config, dossier_base, message_config = charger_configuration()
    fichier_journal = configurer_journalisation(config["journalisation"], dossier_base)
    journal.info("MesurePlan %s — %s — journal : %s", __version__, message_config, fichier_journal)
    sys.excepthook = _journaliser_exception_non_geree

    # 2. Interface (import tardif : erreurs d'installation Qt journalisées proprement)
    try:
        from PySide6.QtCore import QEvent, QLocale
        from PySide6.QtWidgets import QApplication

        from mesureplan.fenetre import FenetrePrincipale
    except ImportError:
        journal.exception("Dépendances graphiques manquantes : installez PySide6 et PyMuPDF")
        sys.exit(2)

    class Application(QApplication):
        """Reçoit aussi les ouvertures de fichiers du Finder macOS (glisser sur l'icône, « Ouvrir avec »)."""

        def __init__(self, argv) -> None:
            super().__init__(argv)
            self.fenetre = None
            self.en_attente: Path | None = None

        def event(self, evenement) -> bool:  # noqa: D401 — API Qt
            if evenement.type() == QEvent.Type.FileOpen:
                chemin = Path(evenement.file())
                if self.fenetre is not None:
                    self.fenetre.ouvrir_pdf(chemin)
                else:
                    self.en_attente = chemin
                return True
            return super().event(evenement)

    # Virgule décimale dans les champs de saisie numériques
    QLocale.setDefault(QLocale(QLocale.Language.French, QLocale.Country.France))
    application = Application(sys.argv)
    application.setApplicationName("MesurePlan")
    application.setOrganizationName("MesurePlan")
    application.setStyle("Fusion")
    try:
        from importlib import resources

        from PySide6.QtGui import QIcon

        # Icône embarquée dans le paquet (fonctionne aussi dans l'exécutable PyInstaller)
        with resources.as_file(resources.files("mesureplan").joinpath("icone.png")) as chemin_icone:
            application.setWindowIcon(QIcon(str(chemin_icone)))
    except (OSError, FileNotFoundError):
        journal.warning("Icône de l'application introuvable")

    fenetre = FenetrePrincipale(config)
    application.fenetre = fenetre
    fenetre.show()
    # Un PDF peut être passé en argument (mesureplan plan.pdf, « Ouvrir avec » Windows/Linux) ou par le Finder
    arguments = [a for a in application.arguments()[1:] if a.lower().endswith(".pdf")]
    if arguments:
        fenetre.ouvrir_pdf(Path(arguments[0]))
    elif application.en_attente is not None:
        fenetre.ouvrir_pdf(application.en_attente)

    code = application.exec()
    journal.info("Fin de session (code %d)", code)
    sys.exit(code)


if __name__ == "__main__":
    main()

# -*- mode: python ; coding: utf-8 -*-
"""Recette PyInstaller de MesurePlan : exécutable autonome, sans Python à installer.

Construction (depuis la racine du projet, sur le système cible) :
    pyinstaller --noconfirm packaging/mesureplan.spec
Résultat dans dist/ :
    Windows : dist/MesurePlan/MesurePlan.exe   (dossier à distribuer en entier)
    macOS   : dist/MesurePlan.app
    Linux   : dist/MesurePlan/MesurePlan
PyInstaller ne fait pas de compilation croisée : chaque système construit son propre exécutable
(voir .github/workflows/executables.yml pour la construction automatique des trois).
"""

import re
import sys
from pathlib import Path

RACINE = Path(SPECPATH).resolve().parent          # noqa: F821 — SPECPATH fourni par PyInstaller
SOURCES = RACINE / "src"
PAQUET = SOURCES / "mesureplan"
VERSION = re.search(r'__version__ = "([^"]+)"', (PAQUET / "__init__.py").read_text(encoding="utf-8")).group(1)

# Modules Qt inutiles : exclus pour alléger fortement l'exécutable
EXCLUS = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtQml",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtMultimedia",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtBluetooth", "PySide6.QtPositioning",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtNetworkAuth",
    "tkinter", "matplotlib", "numpy", "pytest",
]

analyse = Analysis(  # noqa: F821
    [str(Path(SPECPATH) / "lanceur.py")],         # noqa: F821
    pathex=[str(SOURCES)],
    datas=[(str(PAQUET / "config_defaut.json"), "mesureplan"), (str(PAQUET / "icone.png"), "mesureplan")],
    hiddenimports=["PySide6.QtPrintSupport", "pymupdf"],
    excludes=EXCLUS,
    noarchive=False,
)
archive = PYZ(analyse.pure)  # noqa: F821

icone = None
if sys.platform == "win32":
    icone = str(Path(SPECPATH) / "mesureplan.ico")   # noqa: F821
elif sys.platform == "darwin":
    icone = str(Path(SPECPATH) / "mesureplan.icns")  # noqa: F821

executable = EXE(  # noqa: F821
    archive, analyse.scripts, [],
    exclude_binaries=True,
    name="MesurePlan",
    console=False,          # application graphique : pas de fenêtre de terminal
    icon=icone,
    upx=False,              # UPX déclenche des faux positifs antivirus sous Windows
)
dossier = COLLECT(  # noqa: F821
    executable, analyse.binaries, analyse.datas,
    name="MesurePlan",
    upx=False,
)

if sys.platform == "darwin":
    application = BUNDLE(  # noqa: F821
        dossier,
        name="MesurePlan.app",
        icon=icone,
        bundle_identifier="fr.mesureplan.app",
        version=VERSION,
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            # Ouvrir un PDF avec MesurePlan depuis le Finder
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": "Document PDF",
                "CFBundleTypeRole": "Editor",
                "LSItemContentTypes": ["com.adobe.pdf"],
                "LSHandlerRank": "Alternate",
            }],
        },
    )

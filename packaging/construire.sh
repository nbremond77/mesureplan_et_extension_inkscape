#!/usr/bin/env bash
# Construit l'exécutable autonome de MesurePlan sous Linux ou macOS.
# Usage : ./packaging/construire.sh            (depuis la racine du projet)
# Prérequis : Python 3.10+ (uniquement pour CONSTRUIRE ; l'utilisateur final n'en a pas besoin).
set -euo pipefail

RACINE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RACINE"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' src/mesureplan/__init__.py)"
SYSTEME="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"

echo "== Environnement de construction isolé"
python3 -m venv .venv-construction
# shellcheck disable=SC1091
source .venv-construction/bin/activate
python -m pip install --upgrade pip
python -m pip install ".[build,dev]"

echo "== Tests du noyau"
python -m pytest -q

echo "== PyInstaller"
pyinstaller --noconfirm --clean packaging/mesureplan.spec

echo "== Archive"
mkdir -p livraison
if [ "$SYSTEME" = "darwin" ]; then
    ARCHIVE="livraison/MesurePlan-${VERSION}-macos-${ARCH}.zip"
    # ditto conserve les attributs du paquet .app (indispensable sur macOS)
    ditto -c -k --keepParent dist/MesurePlan.app "$ARCHIVE"
else
    ARCHIVE="livraison/MesurePlan-${VERSION}-linux-${ARCH}.tar.gz"
    tar -czf "$ARCHIVE" -C dist MesurePlan
fi
echo "Exécutable prêt : $ARCHIVE"

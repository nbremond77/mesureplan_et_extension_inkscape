# Construit l'exécutable autonome de MesurePlan sous Windows (PowerShell).
# Usage : powershell -ExecutionPolicy Bypass -File packaging\construire.ps1   (depuis la racine du projet)
# Prérequis : Python 3.10+ (uniquement pour CONSTRUIRE ; l'utilisateur final n'en a pas besoin).
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$version = (Select-String -Path "src\mesureplan\__init__.py" -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value

Write-Host "== Environnement de construction isolé"
py -3 -m venv .venv-construction
& .venv-construction\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install ".[build,dev]"

Write-Host "== Tests du noyau"
python -m pytest -q

Write-Host "== PyInstaller"
pyinstaller --noconfirm --clean packaging\mesureplan.spec

Write-Host "== Archive"
New-Item -ItemType Directory -Force -Path livraison | Out-Null
$archive = "livraison\MesurePlan-$version-windows-x64.zip"
Compress-Archive -Path dist\MesurePlan -DestinationPath $archive -Force
Write-Host "Exécutable prêt : $archive  (décompresser puis lancer MesurePlan\MesurePlan.exe)"

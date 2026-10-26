# Prompt de contexte — reprise du projet MesurePlan par une autre IA

> Copiez l'intégralité de ce fichier en tête d'une nouvelle conversation, puis joignez l'archive du
> projet (ou les fichiers concernés). Il décrit le projet, ses conventions, son état réel et la manière
> attendue de travailler.

---

## 1. Rôle attendu

Tu reprends le développement de **MesurePlan**, une application de bureau Python/Qt écrite pour Bernard,
développeur Python et data expérimenté. Toutes les interactions se font **en français**, code, commentaires
et documentation compris. Tu travailles en ingénieur logiciel rigoureux :
- distingue toujours **faits vérifiés**, **hypothèses** et **opinions** ;
- signale ce qui n'a pas pu être testé ;
- privilégie les sources primaires (documentation PyMuPDF et Qt, normes) ;
- expose limites et contre-arguments.

## 2. Le produit

Application de **métré, d'annotation et d'impression à l'échelle de plans PDF vectoriels** (plans
d'architecte, sans accès aux DWG, DXF ou IFC). Version **1.4.0**. Fonctions :

- **Mesures** : distance, distance décomposée « distance XY » (longueur, ΔX, ΔY signés avec Y vers le
  haut, angle aigu par rapport à l'horizontale de la page), chaîne de cotes, surface + périmètre, angle, avec accrochage aux traits
  vectoriels du PDF (extrémités, milieux, intersections, sur trait).
- **Échelle** :
  - lue dans le texte du cartouche (« Échelle 1/100 ») ;
  - corrigée par calibration sur une ou plusieurs cotes connues ;
  - affichage de l'écart au cartouche et de la dispersion entre références.
- **Annotations** : flèche (simple ou double), ligne, polyligne, polygone, rectangle, ovale, cercle, texte.
  Style réglable :
  - trait : couleur, épaisseur, style (plein / tirets / pointillés) ;
  - fond : couleur + opacité, ou transparent ;
  - **24 motifs techniques** (hachures, béton, brique, gravier, terre, gazon, lames de terrasse, bois,
    isolant…), avec angle, échelle, couleur et épaisseur.
- **Édition** (outil Naviguer) :
  - déplacement de tout élément ;
  - poignées de sommets (avec accrochage), ajout de sommet (double-clic sur un côté), suppression
    (Ctrl+clic) ;
  - rotation à la souris (poignée ronde) ou par saisie d'angle, pour rectangles, ovales, lignes et flèches ;
  - le clic droit termine le tracé et revient à l'outil Naviguer ;
  - annuler / rétablir sur 100 niveaux.
- **Export** :
  - CSV ;
  - copie PDF annotée, en mode incrusté ou en annotations PDF natives (repli automatique en incrustation).
- **Impression à l'échelle** :
  - échelle libre, formats A4 à A0, Letter, Tabloid ou personnalisé, orientation automatique ;
  - mosaïque avec recouvrement, repères de feuille et plan d'assemblage ;
  - barre d'échelle et segment de contrôle de 100 mm sur chaque feuille ;
  - sortie en PDF vectoriel ou impression directe à 300 dpi.
- **Distribution** : exécutables autonomes Windows, macOS et Linux via PyInstaller et GitHub Actions.

Un dépôt voisin, `inkscape-mesureplan/`, contient une extension Inkscape 1.2+ (échelle, calibration,
mesures, étiquettes). Elle est indépendante de l'application.

## 3. Conventions de code OBLIGATOIRES

1. **Paramètres applicatifs dans un fichier JSON** (`config/config.json`, fusionné avec
   `src/mesureplan/config_defaut.json`). Aucune constante de réglage en dur si elle peut intéresser
   l'utilisateur.
2. **Dépendances dans `pyproject.toml` (PEP 621)**. Extras `dev` (pytest) et `build` (pyinstaller).
3. **Journalisation `logging` de la bibliothèque standard** :
   - sorties console + `RotatingFileHandler` ;
   - format `horodatage | niveau | utilisateur | module | message` ;
   - niveau lu dans le JSON ;
   - `logger.exception()` dans les `except` ;
   - `getpass.getuser()` injecté dans chaque enregistrement par un filtre personnalisé
     (`journalisation.FiltreUtilisateur`).
4. **Commentaires en français, abondants** ; identifiants en français (`charger_page`, `echelle`…).
5. **Identifiants chiffrés** : convention `store_secure_credentials.py`, avec `config/.secure_store.enc`
   et `config/.secure_key`. *Sans objet actuellement* : aucun secret n'est manipulé. À appliquer si une
   fonction future en introduit (service distant, API…).
6. **Documentation technique en Typst**, compilée en PDF (`docs/*.typ`, gabarit `docs/commun.typ`).

## 4. Architecture (à respecter)

Trois couches. Une couche n'importe que les couches inférieures.

| Couche | Modules | Règle |
|---|---|---|
| Noyau pur | `geometrie`, `echelle`, `mesures`, `annotations`, `motifs`, `impression` | **Aucun import Qt ni PyMuPDF.** Toute la logique métier ici. Testé. |
| Accès PDF | `pdf_document`, `export_pdf`, `impression_pdf` | `import pymupdf` **à l'intérieur des fonctions** (import différé). |
| Présentation | `vue_plan`, `rendu_elements`, `fenetre`, `panneaux`, `panneau_annotations`, `dialogue_impression`, `icones`, `app` | PySide6. Pas de calcul métier. |
| Transverse | `config`, `journalisation` | — |

**Principe clé : fidélité écran ↔ PDF.** Les contours (`Annotation.contour()`), pointes de flèches et
motifs (`motifs.generer`) sont calculés une seule fois par le noyau. Ils sont consommés à l'identique par
Qt (`rendu_elements`) et par PyMuPDF (`export_pdf`). Ne jamais dupliquer une géométrie dans la couche
graphique.

## 5. Conventions géométriques

- Repère = **page PDF en points** (1 pt = 1/72 in = 0,3528 mm), origine en haut à gauche, **Y vers le bas**.
  Les pages `/Rotate` sont normalisées en mémoire (`Page.remove_rotation()`) à l'ouverture comme à l'export.
- Toutes les géométries sont **stockées en pt**. L'échelle n'est appliquée qu'au calcul. Corriger l'échelle
  met donc tout à jour sans retracer.
- Échelle : `facteur (m/pt) = N × 0,0254/72` au cartouche 1:N, sinon moyenne des `réel/longueur_pt` des
  références. Échelle supposée **isotrope**.
- **Angles positifs = sens trigonométrique à l'écran.** Fonction `geometrie.tourner`. Qt tourne en sens
  horaire, d'où `QTransform.rotate(-angle)`.
- **Rectangle et ovale** : deux coins *avant rotation* + `angle` autour du centre. **Ligne et flèche** :
  rotation appliquée directement aux points.
- Épaisseurs, polices et pas des motifs sont en **pt « papier »**.

## 6. Données

- **Session** : `plan.pdf.mesures.json`, à côté du PDF.
  - Format 2 ; format 1 toujours lisible.
  - Écriture atomique ; sauvegarde automatique.
  - Identifiants uniques partagés entre mesures et annotations (`prochain_identifiant`).
  - `Style.depuis_dict` ignore les clés inconnues : **ajoute les nouvelles propriétés avec une valeur par
    défaut** pour rester compatible.
- **QSettings** : géométrie de la fenêtre, dernier dossier, dernier style d'annotation.
- **Journal** : `~/.mesureplan/logs/mesureplan.log`, ou relatif au dossier de la configuration.

## 7. État réel et vérifications — À LIRE

**Vérifié dans l'environnement de développement :**
- 42 tests pytest du noyau, tous verts :
  - `tests/test_noyau.py` (18) ;
  - `tests/test_annotations.py` (9) ;
  - `tests/test_impression.py` (5) ;
  - `tests/test_motifs_rotation.py` (10).
- Chaîne complète échelle → accrochage → surface → calibration, sur `exemples/plan_essai.pdf` (traits lus
  par pdfplumber à la place de PyMuPDF). Valeurs obtenues : 44,08 m², 10,00 m, 150°, écart +3,09 %.
- Export PDF et impression exercés avec un **PyMuPDF simulé** (enregistreur d'appels) : tous les types
  d'éléments, deux modes.
- Analyse statique de tous les modules (noms non définis, imports inutilisés).
- Documentation Typst compilée en PDF (typst 0.15).

**NON vérifié (aucun accès à PyPI pendant le développement) :**
- **l'interface PySide6 n'a jamais été lancée** ;
- les **appels réels à PyMuPDF** n'ont jamais été exécutés ;
- PyInstaller et le workflow GitHub Actions n'ont jamais tourné.

Première tâche probable : lancer `mesureplan exemples/plan_essai.pdf`, lire le journal et corriger les
éventuelles erreurs d'API. Les signatures PyMuPDF utilisées sont listées au § 8.

## 8. Points d'API à surveiller au premier lancement

- PyMuPDF :
  - `Page.get_drawings()` (clés `items` : `l`, `c`, `re`, `qu`), `Page.remove_rotation()`,
    `get_pixmap(matrix, clip, alpha)`, `get_text("text")` ;
  - `Shape.draw_*` et `Shape.finish(color, fill, width, dashes, closePath, fill_opacity, lineCap, lineJoin)` ;
  - `insert_text(fontname="helv"/"hebo")` ;
  - `add_line_annot`, `set_line_ends`, `add_polygon_annot`, `add_polyline_annot`, `add_rect_annot`,
    `add_circle_annot`, `add_freetext_annot(text_color, fill_color)`, `set_border(width, dashes=[int])`,
    `set_opacity`, `set_info`, `update` ;
  - `show_pdf_page(rect, src, pno, clip)`, `Document.tobytes()`, `pymupdf.get_text_length`.
- Qt :
  - `QGraphicsView` en `NoAnchor` (zoom compensé à la main) ;
  - éléments `ItemIgnoresTransformations` ;
  - `QPageSize(QSizeF, Unit, nom, FuzzyMatch)` ;
  - `QPrinter.setFullPage(True)` ;
  - `QInputDialog.getMultiLineText` ;
  - `QEvent.Type.FileOpen` (macOS).

## 9. Limites connues

- Police PDF Helvetica (Latin-1). Les caractères hors jeu sont substitués par `annotations.texte_pdf`.
- Annotations PDF natives : une seule opacité par annotation ; les motifs y sont incrustés dessous.
- Texte non orientable. Pas de calques ni de groupes. Échelle isotrope.
- Exécutables non signés : alerte SmartScreen sous Windows, Gatekeeper sous macOS.
- Licence **AGPL** imposée par PyMuPDF.

## 10. Pistes d'évolution (backlog)

1. Recette de l'interface et corrections du premier lancement (prioritaire).
2. Tests d'interface `pytest-qt`, et tests d'export contre le vrai PyMuPDF (CI).
3. Lignes de cote architecturales (cotation automatique avec flèches et textes alignés).
4. Métré par pièce : tableau exportable en `.xlsx`.
5. Calques, groupes, verrouillage d'éléments ; orientation du texte.
6. Import DXF ou SVG ; motifs définis par fichier JSON utilisateur.
7. Signature des exécutables ; AppImage pour Linux.

## 11. Manière de travailler attendue

- Toute nouvelle logique va dans le **noyau pur** avec ses **tests**. La couche Qt ne fait qu'afficher et
  relayer.
- Conserver la compatibilité du format de session : nouvelles clés avec valeur par défaut, et `format`
  incrémenté si la structure change.
- Mettre à jour `README.md`, `docs/guide_utilisateur.typ`, `docs/dat.typ` et ce fichier à chaque
  évolution notable. Incrémenter `__version__` et la version de `pyproject.toml`.
- Signaler explicitement ce qui n'a pas pu être exécuté.

## 12. Carte des fichiers

```
mesureplan/
├── pyproject.toml            dépendances PEP 621, extras dev/build, point d'entrée « mesureplan »
├── config/config.json        configuration de développement (copie de config_defaut.json)
├── src/mesureplan/
│   ├── geometrie.py          noyau : géométrie, index spatial, accrochage, rotation
│   ├── echelle.py            noyau : cartouche, calibration, détection d'échelle
│   ├── mesures.py            noyau : Mesure, Session (JSON v2), CSV, formatage FR
│   ├── annotations.py        noyau : Annotation, Style, contour, rotation, poignées
│   ├── motifs.py             noyau : 24 motifs + découpe exacte par le contour
│   ├── impression.py         noyau : mise en page à l'échelle, mosaïque
│   ├── pdf_document.py       PyMuPDF : rendu, traits, texte
│   ├── export_pdf.py         PyMuPDF : copie annotée (incrusté / annotations)
│   ├── impression_pdf.py     PyMuPDF : PDF d'impression imposé
│   ├── vue_plan.py           Qt : interaction, accrochage, édition
│   ├── rendu_elements.py     Qt : éléments graphiques (rotation, motifs en cache)
│   ├── fenetre.py            Qt : fenêtre principale, historique, export, impression
│   ├── panneaux.py           Qt : panneaux Échelle et Mesures
│   ├── panneau_annotations.py Qt : style, motif, orientation ; dialogue d'export
│   ├── dialogue_impression.py Qt : dialogue d'impression, impression directe
│   ├── icones.py             Qt : icônes dessinées par programme
│   ├── app.py, __main__.py   point d'entrée (ouverture de fichier macOS comprise)
│   ├── config.py, journalisation.py
│   └── config_defaut.json, icone.png
├── tests/                    42 tests pytest du noyau
├── exemples/plan_essai.pdf   plan à cotes connues (3 pages)
├── docs/                     dat.typ/.pdf, guide_utilisateur.typ/.pdf, commun.typ, images/
├── packaging/                mesureplan.spec (PyInstaller), construire.sh/.ps1, icônes, .desktop
├── .github/workflows/executables.yml   construction Windows / macOS (arm64, x86_64) / Linux
└── CONTEXTE_IA.md            ce fichier
```

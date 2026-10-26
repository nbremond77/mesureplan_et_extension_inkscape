# MesurePlan

Métré à l'échelle et annotation de plans PDF **vectoriels** : distances, chaînes de cotes, surfaces +
périmètres, angles ; flèches, lignes, formes et textes ; export d'une copie PDF annotée.
Accrochage aux traits du plan (extrémités, milieux, intersections), échelle lue dans le cartouche puis
corrigée par calibration sur une ou plusieurs cotes connues, avec contrôle de cohérence.

Fonctionne sous Linux, Windows et macOS (Python ≥ 3.10, PySide6, PyMuPDF).

## Installation (Manjaro)

```bash
cd mesureplan
python -m venv .venv && source .venv/bin/activate
pip install -e .            # ou : pip install -e ".[dev]" pour lancer les tests
mesureplan exemples/plan_essai.pdf
```

Sans environnement virtuel, les paquets `python-pyside6` et `python-pymupdf` des dépôts Manjaro
conviennent : `PYTHONPATH=src python -m mesureplan`.

## Mode d'emploi express

1. **Ouvrir** le PDF (Ctrl+O ou glisser-déposer). L'échelle du cartouche est lue automatiquement si le
   texte du plan contient « Échelle 1/100 », « Ech. 1:50 »… Sinon, saisissez-la dans le panneau *Échelle*.
2. **Calibrer** (C) : cliquez les deux extrémités d'une cote écrite sur le plan, saisissez sa valeur.
   Ajoutez une 2ᵉ cote, perpendiculaire si possible : le panneau affiche l'écart au cartouche et la
   cohérence entre références. Toutes les mesures sont recalculées instantanément.
3. **Mesurer** : D distance · X distance décomposée · L chaîne · S surface · A angle.
   - **Distance XY** (X) : longueur, ΔX horizontal, ΔY vertical et angle aigu par rapport à
     l'horizontale de la page, avec le triangle de décomposition tracé en tirets. Dans l'export CSV,
     ΔX et ΔY sont signés (droite et haut positifs).
   - accrochage automatique : ■ extrémité, ▲ milieu, ✕ intersection, ⧖ sur le trait ;
   - **Ctrl** maintenu : point libre · **Maj** : direction contrainte (pas de 45°, configurable) ;
   - **Entrée** / double-clic / clic droit : termine une chaîne ou ferme une surface ;
   - **Retour arrière** : retire le dernier point · **Échap** : annule.
4. **Exploiter** : tableau des mesures (renommer avec F2 : le nom s'affiche sur le plan, ex. « Séjour »),
   totaux de la page ou de la sélection, export CSV (Ctrl+E, séparateur `;` et virgule décimale).

5. **Annoter** (deuxième barre d'outils) :

   | Touche | Outil | Geste |
   |--------|-------|-------|
   | W | Flèche | glisser de la queue vers la pointe (Maj : angle contraint) |
   | I | Ligne | glisser (Maj : angle contraint) |
   | Y | Polyligne | clics, double-clic / Entrée pour terminer |
   | G | Polygone | clics, double-clic / Entrée pour fermer |
   | Q | Rectangle | glisser d'un coin à l'autre (Maj : carré) |
   | E | Ovale | glisser la boîte englobante (Maj : cercle) |
   | O | Cercle | glisser du centre vers le bord |
   | T | Texte | clic au coin haut-gauche, saisie multiligne |

   Le panneau *Annotations* règle la couleur du trait (palette rapide : clic = trait, Maj+clic = fond),
   l'épaisseur, le style (plein / tirets / pointillés), le fond (couleur et opacité, ou transparent),
   la taille du texte et son cadre, ainsi que la double pointe des flèches. Ces réglages s'appliquent au prochain
   tracé **et** aux annotations sélectionnées. En mode navigation, cliquer sélectionne, glisser déplace
   (Maj : horizontal/vertical), double-clic modifie un texte (ou renomme une mesure). L'accrochage
   fonctionne aussi pour les annotations : une flèche peut pointer exactement un angle de mur.
6. **Exporter en PDF** (Ctrl+Maj+P) : copie du plan avec annotations, mesures et, si souhaité, les cotes
   de référence. Deux modes :
   - *incrusté* : rendu identique dans toutes les visionneuses, non modifiable ;
   - *annotations PDF* : objets standard, déplaçables et supprimables dans Okular, Acrobat ou Xournal++.

   Le plan d'origine n'est jamais modifié.

7. **Imprimer à l'échelle** (Ctrl+P), pour la page courante entière ou la zone affichée à l'écran :
   - échelle d'impression au choix (1:20, 1:50, 1:100, 1:200… ou saisie libre), indépendante de
     l'échelle du plan : un plan au 1:100 peut s'imprimer au 1:50 ;
   - formats A4, A3, A2, A1, A0, Letter, Tabloid ou personnalisé ; orientation automatique (moins de
     feuilles) ou imposée ; marges réglables ;
   - **mosaïque** si la zone dépasse la feuille : découpage avec recouvrement réglable, lignes de
     recouvrement et repères de feuille (A1, A2, B1…), page de plan d'assemblage ;
   - sur chaque feuille : légende, **barre d'échelle** graduée et **segment de contrôle de 100 mm** ;
   - résumé en direct : dimensions réelles et imprimées, nombre de feuilles, alerte si l'échelle n'est
     pas calibrée.

   L'impression utilise l'**échelle calibrée** : un PDF reçu « ajusté à la page » est corrigé
   automatiquement. Deux sorties possibles :
   - *Créer le PDF* (recommandé) : PDF vectoriel, net à toute échelle, à imprimer depuis la visionneuse
     **à 100 % / taille réelle** ;
   - *Imprimer…* : envoi direct à l'imprimante, avec un rendu à 300 dpi.

   Mesurez toujours le segment de contrôle avec une règle : un pilote qui redimensionne la page fausse
   l'échelle sans prévenir.

8. **Modifier** (outil Naviguer, touche N) :
   - glisser une mesure ou une annotation la déplace (Maj : horizontal ou vertical) ;
   - poignées carrées : déplacement des sommets avec accrochage, coins des rectangles et ovales ;
   - poignée ronde : rotation des rectangles, ovales, lignes et flèches (Maj : pas de 15°). L'angle se
     saisit aussi dans le panneau *Annotations* ;
   - Ctrl+clic sur une poignée supprime le sommet ; double-clic sur un côté en ajoute un ;
   - **clic droit** : termine le tracé en cours et revient à l'outil Naviguer.
9. **Motifs de remplissage** pour rectangles, ovales, cercles et polygones. 24 motifs : hachures simples,
   croisées, acier, maçonnerie, béton, béton armé, brique, parpaing, pierre, enrobé, gravier, sable, terre,
   terre végétale, végétalisation, lames de terrasse, parquet, bois (fil et en coupe), isolant souple et
   rigide, carrelage, eau, pointillé. Angle, échelle, couleur et épaisseur sont réglables. Le motif est
   découpé exactement par le contour, identique à l'écran et dans le PDF (planche :
   `docs/images/motifs.png`).

**Ctrl+Z / Ctrl+Y** annulent et rétablissent toute modification (mesures, annotations, échelle).
Épaisseurs et tailles de police sont en points « papier » : ce que l'on voit est ce qui sera exporté.

Les mesures sont enregistrées automatiquement dans `plan.pdf.mesures.json`, à côté du PDF. Elles sont
stockées en coordonnées PDF : corriger l'échelle ne nécessite jamais de retracer.

Navigation : molette = zoom sous le curseur · bouton du milieu ou Espace+glisser = déplacer ·
F = page entière · Pg.préc./Pg.suiv. Le rendu est recalculé en haute définition sur la zone visible.

## Exécutables sans Python (Windows, macOS, Linux)

PyInstaller ne compile pas d'un système vers un autre. Deux possibilités :

- **Automatique (recommandé)** : pousser le projet sur GitHub, puis lancer le workflow *Exécutables*
  (onglet Actions) ou créer une étiquette `v1.3.0`. Il construit et publie :
  - `MesurePlan-windows-x64.zip` ;
  - `MesurePlan-macos-arm64.zip` et `MesurePlan-macos-x86_64.zip` ;
  - `MesurePlan-linux-x86_64.tar.gz`.
- **Local**, sur le système cible :
  - Linux ou macOS : `./packaging/construire.sh` ;
  - Windows : `powershell -ExecutionPolicy Bypass -File packaging\construire.ps1`.

L'utilisateur final décompresse l'archive et lance `MesurePlan` (`MesurePlan.exe` sous Windows,
`MesurePlan.app` sous macOS). Les exécutables ne sont pas signés : avertissement SmartScreen ou Gatekeeper
au premier lancement (voir le guide utilisateur).

## Documentation

- `docs/guide_utilisateur.pdf` : guide complet, avec la planche des motifs et les raccourcis.
- `docs/dat.pdf` : dossier d'architecture technique (modules, données, algorithmes, qualité,
  déploiement, risques).
- `CONTEXTE_IA.md` : prompt de contexte pour reprendre le développement avec une autre IA.
- Sources Typst : `docs/*.typ` ; recompilation avec `typst compile docs/guide_utilisateur.typ`.

## Plan d'essai

`exemples/plan_essai.pdf` contient une maison de 10,00 × 8,00 m hors tout (murs de 0,20 m, cloison
à 6,00 m, séjour 5,80 × 7,60 = 44,08 m², mur biais à 150°) :

| Page | Contenu | Comportement attendu |
|------|---------|----------------------|
| 1 | 1:100 exact | façade = 10,00 m, séjour = 44,08 m² |
| 2 | 1:50, page tournée de 90° | mêmes valeurs après lecture du cartouche |
| 3 | cartouche 1/100 mais imprimé à 97 % | 9,70 m avant calibration ; écart +3,09 % signalé ; 10,00 m après |

## Configuration

`config/config.json` (lancement depuis le dossier du projet), sinon `~/.mesureplan/config/config.json`
(créé au premier lancement), ou le fichier désigné par `MESUREPLAN_CONFIG`. Clés principales :

| Section | Clé | Rôle |
|---------|-----|------|
| `journalisation` | `niveau`, `fichier`, `taille_max_octets`, `nombre_sauvegardes` | journal console + fichier tournant |
| `accrochage` | `tolerance_pixels`, `extremites`, `milieux`, `intersections`, `sur_trait` | comportement du « magnétisme » |
| `contrainte` | `pas_angle_degres` | pas de la touche Maj |
| `echelle` | `denominateur_defaut`, `detection_automatique`, `seuil_alerte_ecart_pct`, `seuil_alerte_dispersion_pct` | échelle et alertes |
| `affichage` | `unite_longueur`, `decimales_*`, couleurs | présentation |
| `session` | `sauvegarde_auto`, `suffixe_fichier` | persistance |
| `export` | `separateur_csv`, `separateur_decimal`, `encodage` | CSV |

Aucun identifiant ni secret n'est manipulé : le stockage chiffré des identifiants n'a pas lieu d'être ici.

## Tests

```bash
pip install -e ".[dev]" && pytest
```

Les tests couvrent le noyau (géométrie, accrochage, extraction des traits, échelle, détection du
cartouche, session, CSV) et le modèle d'annotations (géométrie, sélection, pointes de flèches, persistance,
conversion des mesures pour l'export) et la mise en page d'impression (agrandissement, orientation,
mosaïque et recouvrement, barre d'échelle), sans dépendance graphique.

## Limites connues

- **Hypothèse d'échelle isotrope** : un seul facteur pour X et Y. Si deux cotes perpendiculaires donnent
  une dispersion élevée, le PDF est déformé ; les angles mesurés sont alors faux eux aussi.
- **Plans scannés** : mesure possible, mais sans accrochage (aucun trait vectoriel).
- La détection du cartouche est une **aide**, pas une preuve : un PDF exporté « ajusté à la page » garde
  la mention « 1/100 » tout en étant faux. Calibrez toujours.
- Une surface dont le contour se croise est signalée (⚠) : son aire est fausse.
- **Impression** : l'exactitude finale dépend de l'imprimante (marges matérielles, mise à l'échelle du
  pilote, retrait du papier ≈ 0,1 à 0,5 %). Le segment de contrôle permet de la vérifier. Les annotations
  sont toujours incrustées dans le PDF d'impression.
- **Export PDF** : les textes utilisent la police Helvetica standard du PDF (jeu Latin-1). Les accents
  français, « ² » et « ° » passent ; les autres caractères sont substitués (Σ → « Tot. ») ou remplacés par « ? ».
  Les pages tournées sont exportées avec un aspect identique, mais l'attribut de rotation est ramené à 0.
- **Mode annotations PDF** : une annotation n'a qu'une opacité globale. Une forme à fond semi-transparent
  voit donc aussi son trait atténué. L'aspect des textes libres varie légèrement selon la visionneuse. Le mode
  incrusté est la référence visuelle.
- **Licence** : PyMuPDF est sous AGPL v3. Usage personnel sans contrainte ; en cas de diffusion de
  l'application, le code doit rester sous licence compatible AGPL.

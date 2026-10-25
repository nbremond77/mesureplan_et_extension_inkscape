# Extension Inkscape « Mesure de plan »

Métré à l'échelle dans Inkscape 1.2+ : échelle du cartouche (saisie ou lue dans le texte du plan),
calibration sur une ou plusieurs cotes connues, mesure de longueurs, surfaces, périmètres et angles,
avec étiquettes posées dans un calque « Mesures ».

## Installation

1. Trouver le dossier des extensions utilisateur : *Édition › Préférences › Système › Extensions
   utilisateur* (sous Manjaro : `~/.config/inkscape/extensions/`).
2. Y copier le dossier `inkscape-mesureplan` complet : les `.inx`, `.py` et `mesureplan_config.json`.
3. Redémarrer Inkscape. Le menu *Extensions › Mesure de plan* apparaît.

## Mode d'emploi

**Préparer le plan.** Ouvrez le PDF avec *Fichier › Ouvrir* et gardez la taille de page d'origine. Pour
que l'échelle du cartouche puisse être lue, choisissez une importation qui conserve les textes
(option de gestion du texte de la boîte d'import PDF). Si le texte devient des tracés, saisissez
l'échelle à la main. Activez l'accrochage (touche `%`) aux **nœuds**, **intersections de chemins** et
**milieux de segments**.

**Échelle.** *Extensions › Mesure de plan › 1. Échelle du cartouche…* : saisie (« 1 : 100 ») ou lecture
automatique. L'échelle est mémorisée **dans le document** (élément `<metadata id="mesureplan-echelle">`).

**Calibration (fortement recommandée).** Avec l'outil Plume (B), tracez un trait d'une extrémité à
l'autre d'une cote écrite sur le plan (2 clics accrochés), puis lancez *2. Calibrer sur une cote…* et
saisissez la valeur. Le mode **Ajouter** permet d'utiliser plusieurs cotes : la moyenne est appliquée et
la dispersion est affichée, ce qui détecte une cote mal pointée ou un plan déformé.

**Mesurer.**
- *3. Mesurer la sélection* : action immédiate, sans boîte de dialogue.
  - tracé fermé (rectangle, polygone, chemin avec Z) → surface + périmètre ;
  - 2 nœuds → distance ;
  - plus de nœuds → longueur cumulée Σ ;
  - deux traits sélectionnés → angle entre eux, indiqué dans le résumé.
- *4. Mesurer un angle* : tracé de 3 nœuds (point du 1er bras, sommet, point du 2e bras), ou deux traits.
- *5. Mesurer avec options…* : force le type de mesure, change l'unité ou les décimales, désactive les
  étiquettes, ajoute les résultats à un CSV.

Pour les surfaces de pièces, tracez le contour avec la Plume (clics accrochés aux angles, fermeture sur
le premier point) ou sélectionnez directement un rectangle existant du plan. **Ctrl+clic** sélectionne
un objet à l'intérieur d'un groupe : les imports PDF sont très groupés.

**Aller vite.** Associez des raccourcis aux entrées du menu dans *Édition › Préférences › Interface ›
Raccourcis clavier*, en cherchant « Mesurer ». Inkscape propose aussi par défaut « Extension
précédente » (Alt+Q) pour rejouer la dernière mesure.

## Configuration : `mesureplan_config.json`

| Clé | Rôle |
|-----|------|
| `journalisation.niveau` / `niveau_console` | niveau du fichier journal (`logs/mesureplan.log`) et de la console. Gardez la console sur ERROR : Inkscape affiche stderr dans une fenêtre d'alerte. |
| `echelle.denominateur_defaut` | échelle appliquée tant qu'aucune n'est définie |
| `affichage.unite`, `decimales`, `decimales_surface`, `decimales_angle` | format des résultats |
| `affichage.taille_police_mm`, `couleur_etiquettes`, `couleur_reference` | aspect des étiquettes (taille en mm papier) |
| `affichage.resume_en_mode_rapide` | affiche aussi le résumé pour une mesure rapide unique |

## Tests

`pytest` depuis ce dossier : il teste `mesureplan_calcul.py` (unités du document, aplatissement des
courbes, surfaces, échelle et calibration, angles, détection du cartouche) sans Inkscape.

## Limites

- Échelle supposée identique en X et Y (vérifiable par deux cotes perpendiculaires en mode Ajouter).
- Les surfaces de chemins à plusieurs sous-chemins sont mesurées séparément (pas de soustraction des trous).
- Les courbes de Bézier sont discrétisées en 16 segments : l'erreur sur un quart de cercle est inférieure à 0,1 %.
- Outil natif complémentaire : l'outil Mesure d'Inkscape (M) donne longueurs et angles en direct. Pour un
  plan au 1:100 dont le document est en mm, réglez son facteur d'échelle à 10 000 %. Il n'utilise pas la calibration.

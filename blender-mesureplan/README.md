# MesurePlan 3D — extension Blender

Les outils de mesure de MesurePlan, en 3D, dans la vue 3D de Blender :

| Outil | Résultat |
|-------|----------|
| **Distance** | longueur entre deux points |
| **Distance XYZ** | longueur, **ΔX, ΔY, ΔZ** (signés), longueur horizontale, **pente** (° et %), angle en plan. Les composantes sont dessinées en tirets aux couleurs des axes de Blender (X rouge, Y vert, Z bleu). |
| **Chaîne** | longueur cumulée, longueur horizontale cumulée, dénivelé début → fin |
| **Surface** | surface **vraie**, surface **projetée sur XY** (au sol), périmètre, pente du plan, alerte si le polygone n'est pas plan |
| **Angle** | angle dans l'espace entre deux bras (point, sommet, point) |
| **Calibrer** | corrige l'échelle d'un modèle importé à partir d'une distance connue |

Blender 4.2 ou plus récent (extension). Blender 4.0 et 4.1 : installation « addon » classique.

## Installation

- **Blender 4.2+** : *Édition › Préférences › Get Extensions*, menu ⌄ en haut à droite ›
  *Install from Disk…*, puis choisir `mesureplan_3d-1.0.0.zip`. Le glisser-déposer du zip dans Blender
  fonctionne aussi.
- **Blender 4.0 / 4.1** : *Préférences › Add-ons › Install…*, puis choisir
  `mesureplan_3d-1.0.0-addon.zip`, et cocher « MesurePlan 3D ».
- **Reconstruire le zip d'extension** :
  `blender --command extension build --source-dir mesureplan_3d --output-dir .`

## Utilisation

L'onglet **MesurePlan** se trouve dans la barre latérale de la vue 3D (touche N).

1. Cliquer sur un outil, puis sur les points dans la vue 3D. L'accrochage est automatique, avec un carré
   coloré pour chaque cible :
   - vert : sommet, ou point d'une mesure existante ;
   - bleu : milieu d'arête ;
   - violet : point sur une arête ;
   - orange : point sur une face ;
   - gris : point libre (sur le sol Z = 0 pour le premier point, puis dans le plan perpendiculaire à la vue).
2. Pendant le tracé :
   - **Ctrl** maintenu : pas d'accrochage ;
   - **X / Y / Z** : verrou sur un axe (une 2e pression le retire). Le verrou Z s'utilise depuis une vue de
     côté ou en perspective ; en vue de dessus, la souris ne peut pas le guider ;
   - **Retour arrière** : retire le dernier point ;
   - **Entrée** ou **clic droit** : termine une chaîne ou une surface ;
   - **Échap** : quitte ;
   - molette et bouton du milieu restent disponibles pour naviguer.
3. **Depuis la sélection** (mode Édition) : mesure directement les sommets sélectionnés, dans l'ordre de
   sélection (Maj+clic un par un), ou les faces sélectionnées pour une surface (une mesure par face, avec
   le total affiché).
4. Le panneau **Mesures** liste les mesures :
   - nom modifiable, visibilité ;
   - détail complet de la mesure active ;
   - centrer la vue, supprimer, exporter en **CSV** (« ; » et virgule décimale ; ΔX, ΔY, ΔZ signés).

### Repère
- **Global** : axes de la scène.
- **Objet** : axes d'un objet de référence, par exemple un bâtiment tourné de 30°. Les ΔX et ΔY
  correspondent alors aux façades.

### Échelle et calibration
Valeur réelle = unités Blender × *Unit Scale* de la scène × facteur de calibration.

Pour un modèle importé à la mauvaise échelle (OBJ, DXF, IFC…) :
1. **Calibrer** : cliquer les deux extrémités d'une cote connue et saisir sa valeur. Toutes les mesures
   sont recalculées.
2. Facultatif : **Appliquer aux objets sélectionnés**. Les objets sont mis à l'échelle autour du curseur
   3D, les mesures suivent, et le facteur revient à 1.

Les mesures sont enregistrées **dans le fichier .blend** : coordonnées monde, valeurs recalculées à
l'affichage. Elles sont aussi couvertes par Annuler / Rétablir (Ctrl+Z).

## Configuration et journal

- **Fichier de configuration** : `config.json`, dans le dossier utilisateur de l'extension
  (`…/extensions/.user/user_default/mesureplan_3d/config/`), créé au premier lancement à partir de
  `config_defaut.json`. Il règle la tolérance d'accrochage, les types d'accrochage, les couleurs, la taille
  du texte, les décimales et le niveau du journal.
- **Journal** : `…/mesureplan_3d/logs/mesureplan_3d.log`, en fichier tournant.
- **Installation « addon » (4.0 / 4.1)** : ces deux dossiers sont sous `~/.mesureplan_3d/`.

## Tests

`pytest tests/` (depuis ce dossier). Les 11 tests portent sur le noyau `calcul3d.py`, sans Blender :
composantes et repère tourné, surfaces inclinées et planéité, chaîne, angle, accrochage, pointillés,
formatage, CSV.

## Limites connues

- **Développé sans accès à Blender.** Le noyau est testé. La couche Blender a été exécutée contre une
  *simulation* de l'API (enregistrement, outil modal, accrochage, dessin, calibration, export,
  sélection), pas dans Blender lui-même. À valider au premier lancement : journal, puis console système
  (*Fenêtre › Afficher/Masquer la console système* sous Windows).
- **Dessin en surimpression écran** : les mesures restent visibles à travers les objets. Un segment dont
  une extrémité passe derrière la caméra n'est pas dessiné.
- **Accrochage en mode Édition** : il utilise la géométrie évaluée de la scène. Les dernières
  modifications non validées du maillage peuvent ne pas être prises en compte avant une mise à jour.
- **Rendu** : les mesures n'apparaissent pas au rendu (Cycles/EEVEE). Une conversion en objets
  (courbes + textes) est une évolution possible.
- **Licence** : GPL-3.0-or-later, exigée pour les extensions Blender.

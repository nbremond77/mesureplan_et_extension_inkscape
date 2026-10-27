#import "commun.typ": *

#show: gabarit.with(
  titre: "MesurePlan 3D pour Blender",
  sous-titre: "Guide de l'extension — mesures ΔX, ΔY, ΔZ, pentes, surfaces et calibration dans la vue 3D",
  version: "1.0.0",
  date: "27 octobre 2026",
)

= Présentation

MesurePlan 3D reprend les outils de MesurePlan dans la vue 3D de Blender. Il est conçu pour relever des
cotes sur une maquette (bâtiment modélisé, scan, import IFC, OBJ ou DXF) :

#table(
  columns: (auto, 1fr),
  [Outil], [Résultat],
  [Distance], [Longueur entre deux points.],
  [Distance XYZ], [Longueur ; *ΔX, ΔY, ΔZ* signés ; longueur horizontale ; *pente* en degrés et en pourcentage ; angle en plan avec l'axe X. Les trois composantes sont dessinées en tirets aux couleurs des axes de Blender : X rouge, Y vert, Z bleu.],
  [Chaîne], [Longueur cumulée, longueur horizontale cumulée, dénivelé entre le premier et le dernier point.],
  [Surface], [Surface *vraie* et surface *projetée au sol* (plan XY), périmètre, pente du plan, alerte si le contour n'est pas plan.],
  [Angle], [Angle dans l'espace entre deux bras : un point, le sommet, un point.],
  [Calibrer], [Corrige l'échelle d'un modèle importé à partir d'une cote connue.],
)

#conseil[Pour un pan de toit, l'outil *Surface* donne directement la surface de couverture (vraie) et
l'emprise au sol (projetée), ainsi que la pente du pan.]

== Installation
#table(
  columns: (auto, 1fr),
  [Blender], [Procédure],
  [4.2 et suivants], [*Édition › Préférences › Get Extensions*, menu ⌄ › *Install from Disk…*, puis `mesureplan_3d-1.0.0.zip`. On peut aussi glisser le zip dans la fenêtre de Blender.],
  [4.0 et 4.1], [*Préférences › Add-ons › Install…*, puis `mesureplan_3d-1.0.0-addon.zip`, et cocher « MesurePlan 3D ».],
)
L'onglet *MesurePlan* apparaît dans la barre latérale de la vue 3D (touche #touche[N]).

= Mesurer

+ Cliquer sur un outil du panneau *Mesurer*.
+ Cliquer les points dans la vue 3D. La valeur s'affiche en direct près du curseur.
+ L'outil se termine seul après 2 points (distances, calibration) ou 3 points (angle). Pour une chaîne ou
  une surface : #touche[Entrée] ou clic droit.

== Accrochage
Le point se colle automatiquement à la géométrie. Le carré coloré indique la cible :
#table(
  columns: (auto, 1fr),
  [Couleur], [Cible],
  [vert], [Sommet d'un objet, ou point d'une mesure existante (pour enchaîner).],
  [bleu], [Milieu d'une arête.],
  [violet], [Point sur une arête.],
  [orange], [Point sur une face.],
  [gris], [Point libre : sur le sol (Z = 0) pour le premier point, ensuite dans le plan perpendiculaire à la vue passant par le point précédent.],
)

== Pendant le tracé
#table(
  columns: (auto, 1fr),
  [Touche], [Effet],
  [#touche[Ctrl] maintenu], [Pas d'accrochage : point sur la face touchée, ou point libre.],
  [#touche[X] / #touche[Y] / #touche[Z]], [Verrou sur l'axe correspondant du repère choisi, à partir du point précédent ; une seconde pression le retire. Le verrou #touche[Z] demande une vue de côté ou en perspective : en vue de dessus, la souris ne peut pas le guider.],
  [#touche[Retour arrière]], [Retire le dernier point.],
  [#touche[Entrée] / clic droit], [Termine une chaîne ou une surface ; sinon le clic droit annule le tracé.],
  [#touche[Échap]], [Quitte l'outil.],
  [molette, bouton du milieu, pavé numérique], [Navigation dans la vue, sans interrompre le tracé.],
)

== Depuis la sélection
En mode Édition, les boutons *Depuis la sélection* créent une mesure à partir de la géométrie
sélectionnée :
- *Sommets* : ils sont pris dans l'*ordre de sélection*. Sélectionnez-les un par un (#touche[Maj]+clic)
  pour une chaîne, une surface ou un angle.
- *Surface* avec des faces sélectionnées : une mesure par face, et le total s'affiche dans la barre d'état.

= Repère, échelle et calibration

== Repère
- *Global* : axes de la scène.
- *Objet* : axes d'un objet de référence, sans tenir compte de son échelle. Pour un bâtiment dessiné de
  biais, ΔX et ΔY suivent alors ses façades. Le verrou d'axe suit le même repère.

== Échelle
$ "valeur réelle" = "unités Blender" times "Unit Scale (scène)" times "facteur de calibration" $

== Calibrer un modèle importé
+ *Calibrer* : cliquer les deux extrémités d'une cote connue, puis saisir sa longueur réelle. Le facteur
  est recalculé et toutes les mesures sont mises à jour.
+ Facultatif : *Appliquer aux objets sélectionnés*, en mode Objet. Les objets sont mis à l'échelle
  autour du curseur 3D, et un enfant suit son parent sans être agrandi deux fois. Les mesures suivent, et
  le facteur revient à 1 : le modèle est désormais juste en vraie grandeur.

#attention[Le facteur de calibration s'applique à toutes les mesures de la scène. Réinitialisez-le
(bouton flèche circulaire) avant de mesurer un autre modèle à la bonne échelle.]

= Gérer les mesures

Le panneau *Mesures* permet de :
- renommer une mesure (double-clic sur le nom) et la masquer (icône œil) ;
- afficher le *détail* de la mesure active, avec toutes les valeurs signées et le repère utilisé ;
- afficher le nom de la mesure dans la vue (case « Nom sur la vue ») ;
- centrer la vue sur la mesure, la supprimer, ou supprimer toutes les mesures ;
- *exporter en CSV* : séparateur « ; » et virgule décimale. ΔX, ΔY et ΔZ sont signés, les valeurs sont en
  mètres, m² et degrés, et le repère est précisé.

Les mesures sont *enregistrées dans le fichier .blend* et couvertes par #touche[Ctrl+Z].

= Configuration et dépannage

Le fichier `config.json`, créé au premier lancement dans le dossier utilisateur de l'extension, règle :
la tolérance d'accrochage (12 px), les types d'accrochage, l'épaisseur des traits, la taille du texte,
les couleurs (axes, mesures, aperçu), les décimales, le seuil de planéité et le niveau du journal.

#table(
  columns: (auto, 1fr),
  [Symptôme], [Solution],
  [Les mesures ne s'affichent pas], [Vérifier « Afficher les mesures » et l'icône œil. Consulter `logs/mesureplan_3d.log` : une erreur de dessin y est consignée une fois.],
  [L'accrochage ignore une modification récente en mode Édition], [Repasser brièvement en mode Objet pour mettre à jour la géométrie évaluée.],
  [Valeurs fausses d'un facteur constant], [Vérifier *Unit Scale* (propriétés de la scène › Units) et le facteur de calibration.],
  [Le verrou Z ne réagit pas], [Passer en vue de côté (#touche[1] ou #touche[3] du pavé numérique) ou en perspective.],
)

#attention[Cette extension a été développée sans accès à Blender. Le noyau de calcul est couvert par
11 tests. La couche Blender a été exécutée contre une simulation de l'API (enregistrement, tracé avec
accrochage, dessin, calibration, export, sélection), mais pas dans Blender lui-même. En cas de problème
au premier lancement, transmettez le journal.]

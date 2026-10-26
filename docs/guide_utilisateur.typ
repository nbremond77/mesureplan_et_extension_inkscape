#import "commun.typ": *

#show: gabarit.with(
  titre: "Guide de l'utilisateur",
  sous-titre: "MesurePlan — mesurer, annoter et imprimer à l'échelle des plans PDF",
  version: "1.4.0",
  date: "26 octobre 2026",
)

= Présentation

MesurePlan exploite les plans PDF *vectoriels* reçus d'un architecte ou d'un bureau d'études,
c'est-à-dire des PDF issus d'un logiciel de CAO : les traits restent nets quel que soit le zoom. Il
permet de :
- mesurer distances (y compris décomposées en ΔX, ΔY et angle), chaînes de cotes, surfaces avec périmètre, et angles, à l'échelle du plan ;
- vérifier et corriger l'échelle grâce à des cotes connues ;
- annoter le plan : flèches, lignes, polylignes, polygones, rectangles, ovales, cercles, textes, avec
  couleurs, transparence et motifs techniques (hachures, béton, gravier, lames de terrasse…) ;
- tout modifier après coup : déplacer, éditer les sommets, faire tourner ;
- exporter une copie PDF annotée et imprimer à l'échelle, sur une ou plusieurs feuilles.

Le plan d'origine n'est *jamais modifié*. Mesures et annotations sont enregistrées dans un fichier
voisin, `plan.pdf.mesures.json`.

== Installation
#table(
  columns: (auto, 1fr),
  [Méthode], [Procédure],
  [Exécutable (sans Python)], [Décompresser l'archive de son système. Windows : lancer `MesurePlan\MesurePlan.exe`. macOS : glisser `MesurePlan.app` dans Applications. Linux : lancer `MesurePlan/MesurePlan`.],
  [Depuis les sources], [`python -m venv .venv`, activer, `pip install -e .`, puis `mesureplan plan.pdf`.],
  [Manjaro sans environnement virtuel], [Installer `python-pyside6` et `python-pymupdf`, puis `PYTHONPATH=src python -m mesureplan`.],
)
#attention[Les exécutables ne sont pas signés. Sous Windows, SmartScreen avertit au premier lancement :
« Informations complémentaires » → « Exécuter quand même ». Sous macOS, faire un clic droit sur
l'application → « Ouvrir » la première fois.]

== Plan d'essai
`exemples/plan_essai.pdf` contient une maison de 10,00 × 8,00 m hors tout. Elle a des murs de 0,20 m,
une cloison à 6,00 m, un séjour de 5,80 × 7,60 m (44,08 m²) et un mur biais à 150°.
- *Page 1* : échelle 1:100 exacte.
- *Page 2* : échelle 1:50 sur une page tournée.
- *Page 3* : cartouche 1/100, mais imprimée à 97 %. Elle sert à s'exercer à la calibration.

= L'interface

- *Barre principale* : ouvrir, enregistrer, export CSV, export PDF, impression, annuler / rétablir,
  pages, outils de mesure, cadrage, accrochage, aide.
- *Barre d'annotations* : les huit outils de dessin.
- *Panneaux à droite* :
  - *Échelle* : cartouche, calibration, synthèse ;
  - *Annotations* : style, motif, orientation ;
  - *Mesures* : tableau, totaux, export.
- *Barre d'état* : position réelle du curseur, type d'accrochage, échelle appliquée, consignes de
  l'outil actif.

On ouvre un plan avec #touche[Ctrl+O] ou en *glissant le fichier* dans la fenêtre.

== Se déplacer
#table(
  columns: (auto, 1fr),
  [Geste], [Effet],
  [Molette], [Zoom centré sur le curseur.],
  [Bouton du milieu, ou #touche[Espace] + glisser], [Déplacement de la vue, quel que soit l'outil.],
  [Glisser le fond (outil Naviguer)], [Déplacement de la vue.],
  [#touche[F]], [Page entière.],
  [#touche[+] / #touche[−]], [Zoom avant / arrière.],
  [#touche[Pg.préc.] / #touche[Pg.suiv.]], [Page précédente / suivante.],
)
Le rendu est recalculé en haute définition sur la zone visible : le plan reste net à fort zoom.

= Échelle et calibration

== Échelle du cartouche
À la première ouverture d'une page, MesurePlan cherche dans le texte du plan une mention telle que
« Échelle 1/100 » ou « Ech. 1:50 » et l'applique. Le panneau *Échelle* indique ce qui a été lu. Il signale
aussi les autres échelles présentes, par exemple un détail au 1:20. On peut saisir une autre valeur
(« 1:100 », « 1/100 » ou « 100 », puis #touche[Entrée]).

#attention[Une mention d'échelle n'est pas une garantie. Un PDF exporté ou imprimé « ajusté à la page »
garde la mention 1/100 alors que le dessin a été réduit. *Calibrez toujours.*]

== Calibrer sur une cote connue
+ Choisir l'outil *Calibrer* (#touche[C]).
+ Cliquer les deux extrémités d'une cote écrite sur le plan. L'accrochage aide à viser juste.
+ Saisir la valeur réelle de la cote.

Toutes les mesures sont recalculées immédiatement, sans rien retracer. Le panneau affiche l'échelle
appliquée et l'écart au cartouche (en rouge au-delà de 2 %).

#conseil[Ajoutez une *deuxième cote, perpendiculaire* à la première. La « cohérence des cotes » mesure
l'écart entre elles. Au-delà de 1 %, une cote a été mal pointée ou mal saisie, ou le plan est déformé
(échelles différentes en X et en Y).]

= Mesurer

#table(
  columns: (auto, auto, 1fr),
  [Touche], [Outil], [Utilisation],
  [#touche[D]], [Distance], [Deux clics.],
  [#touche[X]], [Distance XY], [Deux clics. Affiche la longueur, sa composante horizontale ΔX, sa composante verticale ΔY et l'angle par rapport à l'horizontale ; le triangle de décomposition est tracé en tirets.],
  [#touche[L]], [Chaîne], [Clics successifs. La longueur cumulée Σ s'affiche ; double-clic, #touche[Entrée] ou clic droit pour terminer.],
  [#touche[S]], [Surface], [Clics sur les sommets du contour. Donne la surface et le périmètre ; double-clic, #touche[Entrée] ou clic droit pour fermer.],
  [#touche[A]], [Angle], [Un point du premier bras, le sommet, puis un point du second bras.],
)
Pendant le tracé, la valeur s'affiche en direct près du curseur.

== Distance décomposée (ΔX, ΔY, angle)
L'outil *Distance XY* sert à relever un décalage d'implantation, une pente ou un dénivelé sur une coupe.
- *ΔX* et *ΔY* sont les projections horizontale et verticale de la distance, *par rapport à la page*. Elles
  ne suivent pas les axes d'un bâtiment dessiné de biais.
- L'angle affiché est l'angle *aigu* (0 à 90°) avec l'horizontale de la page. Il ne dépend pas de l'ordre
  des deux clics.
- Le tableau et l'étiquette donnent des valeurs absolues. L'export CSV donne ΔX et ΔY *signés* : ΔX positif
  vers la droite, ΔY positif vers le haut.

#conseil[Pour une pente en pourcentage, divisez ΔY par ΔX. Par exemple, ΔY 0,30 m sur ΔX 6,00 m donne
5 %.]

== Accrochage
Le curseur se colle aux traits du PDF. Le symbole affiché indique la cible :
#table(
  columns: (auto, 1fr),
  [Symbole], [Cible],
  [■ carré vert], [Extrémité d'un trait, ou sommet d'une mesure ou d'une annotation existante.],
  [▲ triangle bleu], [Milieu d'un segment.],
  [✕ croix orange], [Intersection de deux traits.],
  [sablier violet], [Point quelconque sur un trait.],
  [\+ petite croix grise], [Point libre.],
)
- #touche[Ctrl] maintenu donne un point libre.
- #touche[Maj] maintenu contraint la direction par pas de 45°.
- #touche[F3] active ou coupe l'accrochage.
- #touche[Retour arrière] retire le dernier point.
- #touche[Échap] annule le tracé.

== Clic droit
Dans n'importe quel outil de tracé, le *clic droit termine le tracé en cours* (s'il comporte assez de
points) *et revient à l'outil Naviguer*. En navigation, le clic droit désélectionne.

= Annoter

== Outils
#table(
  columns: (auto, auto, 1fr),
  [Touche], [Outil], [Geste],
  [#touche[W]], [Flèche], [Glisser de la queue vers la pointe ; #touche[Maj] contraint l'angle.],
  [#touche[I]], [Ligne], [Glisser ; #touche[Maj] contraint l'angle.],
  [#touche[Y]], [Polyligne], [Clics, puis double-clic ou #touche[Entrée].],
  [#touche[G]], [Polygone], [Clics, puis double-clic ou #touche[Entrée] pour fermer.],
  [#touche[Q]], [Rectangle], [Glisser d'un coin à l'autre ; #touche[Maj] donne un carré.],
  [#touche[E]], [Ovale], [Glisser la boîte englobante ; #touche[Maj] donne un cercle.],
  [#touche[O]], [Cercle], [Glisser du centre vers le bord.],
  [#touche[T]], [Texte], [Clic au coin haut-gauche, puis saisie (plusieurs lignes possibles).],
)

== Style
Le panneau *Annotations* règle :
- *Trait* : couleur (sélecteur, ou palette rapide : clic pour le trait, #touche[Maj]+clic pour le
  fond), épaisseur, style (plein, tirets, pointillés), double pointe des flèches.
- *Fond* : couleur et opacité, ou *transparent*.
- *Motif* : voir ci-dessous.
- *Orientation* : voir le chapitre « Modifier ».
- *Texte* : taille, cadre.

Les réglages s'appliquent *au prochain tracé et aux annotations sélectionnées*. Sélectionner une
annotation affiche son style dans le panneau, prêt à être modifié. Épaisseurs et tailles sont en points
« papier » : ce que l'on voit est ce qui sera imprimé.

== Motifs de remplissage
Rectangles, ovales, cercles et polygones peuvent recevoir un motif technique. Ses réglages :
- *angle* : ajouté à l'orientation propre du motif ;
- *échelle* : multiplicateur de l'espacement ;
- *épaisseur* du trait du motif ;
- *couleur* : celle du trait ou une couleur propre.

Le motif est découpé exactement par le contour et suit la rotation de la forme. Il peut se combiner
avec une couleur de fond.

#figure(image("images/motifs.png", width: 100%), caption: [Les 24 motifs, à l'échelle 1 et à l'angle 0.])

#figure(image("images/rotation_motifs.png", width: 85%),
  caption: [Motifs sur des formes tournées : béton armé, lames de terrasse à 30°, isolant, gazon.])

#conseil[Pour un motif dense sur une grande surface, augmentez l'échelle du motif. Au-delà d'environ
25 000 éléments, MesurePlan espace automatiquement le motif pour rester fluide.]

= Modifier

Toutes les modifications se font avec l'outil *Naviguer* (#touche[N] ou #touche[Échap]) :
#table(
  columns: (auto, 1fr),
  [Geste], [Effet],
  [Clic sur un élément], [Sélection. Pour une annotation, son style s'affiche dans le panneau.],
  [Glisser un élément], [Déplacement ; #touche[Maj] le limite à l'horizontale ou à la verticale.],
  [Glisser une poignée carrée], [Déplacement du sommet, avec accrochage (#touche[Ctrl] : libre ; #touche[Maj] : direction contrainte). Sur un rectangle ou un ovale, les coins redimensionnent, le coin opposé restant fixe.],
  [Glisser la poignée ronde], [Rotation des rectangles, ovales, lignes et flèches ; #touche[Maj] : pas de 15°.],
  [#touche[Ctrl] + clic sur une poignée], [Suppression du sommet (chaîne, surface, polyligne, polygone).],
  [Double-clic sur un côté], [Ajout d'un sommet (chaîne, surface, polyligne, polygone).],
  [Double-clic ailleurs], [Modifier le texte d'une annotation, ou renommer une mesure.],
  [#touche[Échap] pendant un glisser], [Annule le glisser.],
  [#touche[Suppr]], [Supprime les éléments sélectionnés.],
  [#touche[Ctrl+Z] / #touche[Ctrl+Y]], [Annuler / rétablir (100 niveaux).],
)
Les mesures éditées affichent leur nouvelle valeur en direct.

L'*orientation* d'une annotation sélectionnée se saisit aussi au clavier dans le panneau *Annotations*,
en degrés, dans le sens trigonométrique. Les boutons −90°, +90° et 0° y sont des raccourcis.

= Exploiter les mesures

Le panneau *Mesures* liste les mesures de la page :
- *Nom* : modifiable avec #touche[F2]. Un nom personnalisé, comme « Séjour », s'affiche sur le plan.
- *Valeur* et *périmètre*.
- *Totaux* : ceux de la sélection, sinon de toute la page.

L'unité des longueurs (m, cm, mm) se choisit en haut du panneau. *Export CSV* (#touche[Ctrl+E]) produit
un fichier avec séparateur « ; » et virgule décimale, lisible directement par un tableur en français.

= Exporter un PDF annoté

#touche[Ctrl+Maj+P] crée une *copie* du plan. Elle contient, au choix, les annotations, les mesures et
les cotes de référence. Deux modes :
- *Incrusté* : rendu identique dans toutes les visionneuses, mais plus modifiable.
- *Annotations PDF* : objets standard, déplaçables et supprimables dans Okular, Acrobat ou Xournal++.
  Les motifs y restent incrustés sous l'annotation.

#attention[La police standard des PDF ne couvre que le jeu Latin-1. Les accents français, « ² » et « ° »
passent ; d'autres caractères sont remplacés (Σ devient « Tot. »).]

= Imprimer à l'échelle

#touche[Ctrl+P] ouvre le dialogue d'impression de la page courante :
- *Échelle d'impression* : libre (1:20, 1:50, 1:100…). Un plan au 1:100 peut s'imprimer au 1:50.
- *Format* : A4 à A0, Letter, Tabloid ou personnalisé.
- *Orientation* : automatique (le moins de feuilles) ou imposée.
- *Marges* réglables.
- *Zone* : la page entière, ou la zone affichée à l'écran (cadrez-la d'abord).
- *Contenu* : annotations et mesures.
- *Repères* : barre d'échelle, segment de contrôle de 100 mm, repères d'assemblage, plan d'assemblage.

Le résumé indique en direct les dimensions réelles et imprimées et le nombre de feuilles. Il alerte si
l'échelle de la page n'a pas été calibrée.

== Mosaïque
Si la zone dépasse la feuille, elle est découpée sur plusieurs feuilles :
- une *bande de recouvrement* réglable est répétée entre feuilles voisines ;
- des lignes pointillées bleues marquent cette bande ;
- chaque feuille porte un repère (A1, A2, B1… : lettre = ligne, chiffre = colonne) ;
- une page « plan d'assemblage » ouvre le document.

== Deux sorties
- *Créer le PDF* (recommandé) : PDF vectoriel, net à toute échelle. On l'imprime depuis sa visionneuse.
- *Imprimer…* : envoi direct à l'imprimante, avec un rendu à 300 dpi.

#attention[Imprimez en *taille réelle / 100 %*, jamais en « ajuster à la page ». Mesurez ensuite à la
règle le *segment de contrôle de 100 mm* : s'il ne mesure pas 100 mm, le pilote a redimensionné la page.
Une imprimante bien réglée garde une imprécision de l'ordre de 0,1 à 0,5 %.]

= Configuration

Le fichier `config.json` se trouve dans `~/.mesureplan/config/`. Il est créé au premier lancement et se
modifie avec un éditeur de texte. On peut aussi désigner un autre fichier par la variable
`MESUREPLAN_CONFIG`.

#table(
  columns: (auto, 1fr),
  [Section], [Réglages utiles],
  [`journalisation`], [Niveau (DEBUG, INFO…), fichier, taille et nombre d'archives du journal.],
  [`accrochage`], [Tolérance en pixels, types d'accrochage actifs.],
  [`contrainte`], [Pas angulaire de la touche #touche[Maj] (45° par défaut).],
  [`echelle`], [Échelle par défaut, lecture automatique du cartouche, seuils d'alerte d'écart et de dispersion.],
  [`affichage`], [Unité, décimales, couleurs, taille des étiquettes.],
  [`session`], [Sauvegarde automatique, suffixe du fichier de mesures.],
  [`export`], [Séparateur CSV, séparateur décimal, encodage.],
)

= Raccourcis clavier

#table(
  columns: (auto, 1fr, auto, 1fr),
  [Touche], [Action], [Touche], [Action],
  [#touche[Ctrl+O]], [Ouvrir], [#touche[N]], [Naviguer],
  [#touche[Ctrl+S]], [Enregistrer], [#touche[D]], [Distance],
  [], [], [#touche[X]], [Distance XY (ΔX, ΔY, angle)],
  [#touche[Ctrl+E]], [Export CSV], [#touche[L]], [Chaîne],
  [#touche[Ctrl+Maj+P]], [Export PDF annoté], [#touche[S]], [Surface],
  [#touche[Ctrl+P]], [Imprimer à l'échelle], [#touche[A]], [Angle],
  [#touche[Ctrl+Z]], [Annuler], [#touche[C]], [Calibrer],
  [#touche[Ctrl+Y]], [Rétablir], [#touche[W]], [Flèche],
  [#touche[Suppr]], [Supprimer la sélection], [#touche[I]], [Ligne],
  [#touche[F]], [Page entière], [#touche[Y]], [Polyligne],
  [#touche[F1]], [Aide], [#touche[G]], [Polygone],
  [#touche[F3]], [Accrochage on/off], [#touche[Q]], [Rectangle],
  [#touche[Espace]], [Déplacer la vue (maintenu)], [#touche[E]], [Ovale],
  [#touche[Échap]], [Annuler / Naviguer], [#touche[O]], [Cercle],
  [#touche[Entrée]], [Terminer le tracé], [#touche[T]], [Texte],
)

= Dépannage

#table(
  columns: (auto, 1fr),
  [Symptôme], [Solution],
  [« Plan sans traits vectoriels »], [Le PDF est un scan. On peut mesurer, mais sans accrochage ; zoomez fortement pour pointer.],
  [Mesures fausses de quelques %], [Plan exporté hors échelle : calibrez sur une cote longue, puis contrôlez sur une seconde.],
  [Cohérence des cotes en rouge], [Vérifiez les cotes saisies et leur pointage. Si l'écart persiste en X et Y, le PDF est déformé : mesurez dans une seule direction après calibration sur cette direction.],
  [Impression à la mauvaise taille], [Option « taille réelle / 100 % » dans la boîte d'impression ; vérifiez le segment de 100 mm.],
  [Le programme ne démarre pas], [Consultez `~/.mesureplan/logs/mesureplan.log` (chaque erreur y est consignée avec sa trace).],
  [Mesures disparues], [Elles sont dans `plan.pdf.mesures.json`, à côté du PDF : conservez ce fichier avec le plan.],
)

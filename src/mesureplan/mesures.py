"""Modèle des mesures et de la session (persistance JSON, export CSV).

Les géométries sont stockées en points PDF : les valeurs réelles sont
recalculées à la volée avec l'échelle courante de la page. Corriger
l'échelle met donc à jour toutes les mesures déjà prises.
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from mesureplan import geometrie as geo
from mesureplan.annotations import Annotation, Style, TypeAnnotation
from mesureplan.echelle import EchellePage

journal = logging.getLogger(__name__)

VERSION_FORMAT_SESSION = 2  # 2 : ajout des annotations (format 1 toujours lisible)

# Facteurs de conversion depuis le mètre pour l'affichage
FACTEURS_UNITE = {"m": 1.0, "cm": 100.0, "mm": 1000.0}


class TypeMesure(str, Enum):
    DISTANCE = "distance"
    DISTANCE_XY = "distance XY"   # distance décomposée : longueur, ΔX, ΔY, angle
    CHAINE = "chaîne"
    SURFACE = "surface"
    ANGLE = "angle"


# Libellés par défaut utilisés pour nommer automatiquement les mesures
LIBELLES = {
    TypeMesure.DISTANCE: "Distance",
    TypeMesure.DISTANCE_XY: "Distance XY",
    TypeMesure.CHAINE: "Chaîne",
    TypeMesure.SURFACE: "Surface",
    TypeMesure.ANGLE: "Angle",
}


@dataclass
class Mesure:
    """Une mesure tracée sur une page."""

    identifiant: int
    type: TypeMesure
    page: int
    points: list[geo.Point]
    nom: str
    nom_personnalise: bool = False

    def valeurs(self, echelle: EchellePage) -> dict[str, float]:
        """Valeurs réelles : longueur (m), surface (m²), périmètre (m), angle (°), ΔX / ΔY (m)."""
        if self.type is TypeMesure.DISTANCE:
            return {"longueur": echelle.longueur_m(geo.distance(self.points[0], self.points[-1]))}
        if self.type is TypeMesure.DISTANCE_XY:
            # ΔX, ΔY signés (Y vers le haut) ; angle aigu par rapport à l'horizontale
            dx, dy, angle, orientation = geo.composantes(self.points[0], self.points[-1])
            return {"longueur": echelle.longueur_m(geo.distance(self.points[0], self.points[-1])),
                    "dx": echelle.longueur_m(dx), "dy": echelle.longueur_m(dy),
                    "angle": angle, "orientation": orientation}
        if self.type is TypeMesure.CHAINE:
            return {"longueur": echelle.longueur_m(geo.longueur_polyligne(self.points))}
        if self.type is TypeMesure.SURFACE:
            return {
                "surface": echelle.surface_m2(geo.aire_polygone(self.points)),
                "perimetre": echelle.longueur_m(geo.longueur_polyligne(self.points, fermee=True)),
            }
        if self.type is TypeMesure.ANGLE:
            # L'angle ne dépend pas de l'échelle (hypothèse : échelle identique en X et Y)
            return {"angle": geo.angle_trois_points(*self.points[:3])}
        raise ValueError(f"Type de mesure inconnu : {self.type}")

    @property
    def avertissement(self) -> str | None:
        """Alerte géométrique éventuelle (ex. surface dont le contour se croise)."""
        if self.type is TypeMesure.SURFACE and geo.polygone_auto_intersecte(self.points):
            return "Contour croisé : surface fausse"
        return None

    def vers_dict(self) -> dict:
        return {
            "identifiant": self.identifiant,
            "type": self.type.value,
            "page": self.page,
            "points": [list(p) for p in self.points],
            "nom": self.nom,
            "nom_personnalise": self.nom_personnalise,
        }

    @classmethod
    def depuis_dict(cls, d: dict) -> "Mesure":
        return cls(
            identifiant=int(d["identifiant"]),
            type=TypeMesure(d["type"]),
            page=int(d["page"]),
            points=[tuple(p) for p in d["points"]],
            nom=str(d.get("nom", "")),
            nom_personnalise=bool(d.get("nom_personnalise", False)),
        )


# ---------------------------------------------------------------------------
# Mise en forme des nombres (convention française)
# ---------------------------------------------------------------------------

def formater_nombre(valeur: float, decimales: int, separateur_decimal: str = ",") -> str:
    """1234.5 → « 1 234,50 » (espace fine insécable pour les milliers)."""
    texte = f"{valeur:,.{decimales}f}"
    return texte.replace(",", " ").replace(".", separateur_decimal)


@dataclass
class Formateur:
    """Convertit les valeurs en texte selon les préférences d'affichage."""

    unite_longueur: str = "m"
    decimales_longueur: dict[str, int] = field(default_factory=lambda: {"m": 2, "cm": 1, "mm": 0})
    decimales_surface: int = 2
    decimales_angle: int = 1

    @classmethod
    def depuis_config(cls, cfg_affichage: dict) -> "Formateur":
        return cls(
            unite_longueur=cfg_affichage.get("unite_longueur", "m"),
            decimales_longueur=dict(cfg_affichage.get("decimales_longueur", {"m": 2, "cm": 1, "mm": 0})),
            decimales_surface=int(cfg_affichage.get("decimales_surface", 2)),
            decimales_angle=int(cfg_affichage.get("decimales_angle", 1)),
        )

    def longueur(self, metres: float, avec_unite: bool = True) -> str:
        u = self.unite_longueur
        texte = formater_nombre(metres * FACTEURS_UNITE[u], self.decimales_longueur.get(u, 2))
        return f"{texte} {u}" if avec_unite else texte

    def surface(self, m2: float, avec_unite: bool = True) -> str:
        texte = formater_nombre(m2, self.decimales_surface)
        return f"{texte} m²" if avec_unite else texte

    def angle(self, degres: float, avec_unite: bool = True) -> str:
        texte = formater_nombre(degres, self.decimales_angle)
        return f"{texte}°" if avec_unite else texte

    def valeur_principale(self, mesure: Mesure, echelle: EchellePage) -> str:
        v = mesure.valeurs(echelle)
        if mesure.type is TypeMesure.SURFACE:
            return self.surface(v["surface"])
        if mesure.type is TypeMesure.ANGLE:
            return self.angle(v["angle"])
        return self.longueur(v["longueur"])

    def detail(self, mesure: Mesure, echelle: EchellePage) -> str:
        """Information complémentaire du tableau des mesures (colonne « Détail »)."""
        v = mesure.valeurs(echelle)
        if "perimetre" in v:
            return f"P {self.longueur(v['perimetre'])}"
        if mesure.type is TypeMesure.DISTANCE_XY:
            return (f"ΔX {self.longueur(abs(v['dx']))} · ΔY {self.longueur(abs(v['dy']))} · "
                    f"{self.angle(v['angle'])}")
        return ""

    def etiquette(self, mesure: Mesure, echelle: EchellePage) -> str:
        """Texte affiché sur le plan (nom seulement s'il a été personnalisé)."""
        v = mesure.valeurs(echelle)
        if mesure.type is TypeMesure.SURFACE:
            lignes = [self.surface(v["surface"]), f"P {self.longueur(v['perimetre'])}"]
        elif mesure.type is TypeMesure.CHAINE:
            lignes = [f"Σ {self.longueur(v['longueur'])}"]
        elif mesure.type is TypeMesure.ANGLE:
            lignes = [self.angle(v["angle"])]
        elif mesure.type is TypeMesure.DISTANCE_XY:
            lignes = [f"L {self.longueur(v['longueur'])}",
                      f"ΔX {self.longueur(abs(v['dx']))}   ΔY {self.longueur(abs(v['dy']))}",
                      f"{self.angle(v['angle'])} / horizontale"]
        else:
            lignes = [self.longueur(v["longueur"])]
        if mesure.nom_personnalise:
            lignes.insert(0, mesure.nom)
        return "\n".join(lignes)


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

def chemin_session_pour(chemin_pdf: Path, suffixe: str = ".mesures.json") -> Path:
    """« plan.pdf » → « plan.pdf.mesures.json » à côté du PDF."""
    return chemin_pdf.with_name(chemin_pdf.name + suffixe)


@dataclass
class Session:
    """Ensemble des échelles et mesures associées à un PDF."""

    chemin_pdf: str
    denominateur_defaut: float = 100.0
    echelles: dict[int, EchellePage] = field(default_factory=dict)
    mesures: list[Mesure] = field(default_factory=list)
    annotations: list[Annotation] = field(default_factory=list)
    prochain_identifiant: int = 1  # compteur commun mesures / annotations : identifiants uniques

    def echelle(self, page: int) -> EchellePage:
        """Échelle de la page (créée à la valeur par défaut si absente)."""
        if page not in self.echelles:
            self.echelles[page] = EchellePage(denominateur_cartouche=self.denominateur_defaut)
        return self.echelles[page]

    def mesures_page(self, page: int) -> list[Mesure]:
        return [m for m in self.mesures if m.page == page]

    def mesure(self, identifiant: int) -> Mesure | None:
        return next((m for m in self.mesures if m.identifiant == identifiant), None)

    def ajouter_mesure(self, type_mesure: TypeMesure, page: int, points: list[geo.Point]) -> Mesure:
        # Numérotation par type et par page : « Surface 3 »
        rang = 1 + sum(1 for m in self.mesures if m.page == page and m.type is type_mesure)
        mesure = Mesure(self.prochain_identifiant, type_mesure, page, list(points),
                        f"{LIBELLES[type_mesure]} {rang}")
        self.prochain_identifiant += 1
        self.mesures.append(mesure)
        journal.info("Mesure ajoutée : %s (page %d, %d points)", mesure.nom, page + 1, len(points))
        return mesure

    def supprimer_mesures(self, identifiants: set[int]) -> int:
        """Supprime mesures ET annotations dont l'identifiant est donné ; retourne le nombre supprimé."""
        avant = len(self.mesures) + len(self.annotations)
        self.mesures = [m for m in self.mesures if m.identifiant not in identifiants]
        self.annotations = [a for a in self.annotations if a.identifiant not in identifiants]
        return avant - len(self.mesures) - len(self.annotations)

    # --- Annotations -----------------------------------------------------------
    def annotations_page(self, page: int) -> list[Annotation]:
        return [a for a in self.annotations if a.page == page]

    def annotation(self, identifiant: int) -> Annotation | None:
        return next((a for a in self.annotations if a.identifiant == identifiant), None)

    def ajouter_annotation(self, type_annotation: TypeAnnotation, page: int, points: list[geo.Point],
                           style: Style, texte: str = "") -> Annotation:
        annotation = Annotation(self.prochain_identifiant, type_annotation, page, list(points), style.copie(), texte)
        self.prochain_identifiant += 1
        self.annotations.append(annotation)
        journal.info("Annotation ajoutée : %s (page %d)", type_annotation.value, page + 1)
        return annotation

    # --- Persistance JSON ------------------------------------------------
    def vers_dict(self) -> dict:
        return {
            "format": VERSION_FORMAT_SESSION,
            "application": "MesurePlan",
            "enregistre_le": datetime.now().isoformat(timespec="seconds"),
            "chemin_pdf": self.chemin_pdf,
            "denominateur_defaut": self.denominateur_defaut,
            "prochain_identifiant": self.prochain_identifiant,
            "echelles": {str(p): e.vers_dict() for p, e in self.echelles.items()},
            "mesures": [m.vers_dict() for m in self.mesures],
            "annotations": [a.vers_dict() for a in self.annotations],
        }

    @classmethod
    def depuis_dict(cls, d: dict) -> "Session":
        if int(d.get("format", 1)) > VERSION_FORMAT_SESSION:
            raise ValueError("Fichier de session produit par une version plus récente")
        session = cls(
            chemin_pdf=str(d.get("chemin_pdf", "")),
            denominateur_defaut=float(d.get("denominateur_defaut", 100.0)),
            echelles={int(p): EchellePage.depuis_dict(e) for p, e in d.get("echelles", {}).items()},
            mesures=[Mesure.depuis_dict(m) for m in d.get("mesures", [])],
            annotations=[Annotation.depuis_dict(a) for a in d.get("annotations", [])],
        )
        identifiant_max = max([m.identifiant for m in session.mesures]
                              + [a.identifiant for a in session.annotations], default=0)
        session.prochain_identifiant = max(int(d.get("prochain_identifiant", 1)), identifiant_max + 1)
        return session

    def enregistrer(self, chemin: Path) -> None:
        # Écriture atomique : fichier temporaire puis remplacement
        temporaire = chemin.with_name(chemin.name + ".tmp")
        temporaire.write_text(json.dumps(self.vers_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        temporaire.replace(chemin)
        journal.debug("Session enregistrée : %s", chemin)

    @classmethod
    def charger(cls, chemin: Path) -> "Session":
        with chemin.open(encoding="utf-8") as flux:
            session = cls.depuis_dict(json.load(flux))
        journal.info("Session chargée : %s (%d mesures)", chemin, len(session.mesures))
        return session

    # --- Export CSV --------------------------------------------------------
    def exporter_csv(self, chemin: Path, formateur: Formateur, separateur: str = ";",
                     separateur_decimal: str = ",", encodage: str = "utf-8-sig") -> int:
        """Exporte toutes les mesures ; retourne le nombre de lignes écrites.

        Les valeurs sont écrites en mètres / m² / degrés (unités SI stables),
        indépendamment de l'unité d'affichage, pour faciliter les reprises tableur.
        """
        def nombre(v: float | None, dec: int = 4) -> str:
            return "" if v is None else f"{v:.{dec}f}".replace(".", separateur_decimal)

        # ΔX positif vers la droite, ΔY positif vers le haut ; angle aigu / horizontale pour « distance XY »
        entetes = ["Page", "Nom", "Type", "Longueur (m)", "ΔX (m)", "ΔY (m)", "Surface (m²)", "Périmètre (m)",
                   "Angle (°)", "Échelle appliquée (1:N)", "Source de l'échelle", "Avertissement",
                   "Points (pt PDF)"]
        lignes = 0
        with chemin.open("w", encoding=encodage, newline="") as flux:
            ecrivain = csv.writer(flux, delimiter=separateur)
            ecrivain.writerow(entetes)
            for m in sorted(self.mesures, key=lambda x: (x.page, x.identifiant)):
                echelle = self.echelle(m.page)
                v = m.valeurs(echelle)
                ecrivain.writerow([
                    m.page + 1, m.nom, m.type.value,
                    nombre(v.get("longueur")), nombre(v.get("dx")), nombre(v.get("dy")),
                    nombre(v.get("surface")), nombre(v.get("perimetre")),
                    nombre(v.get("angle"), 2),
                    nombre(echelle.denominateur_effectif, 2), echelle.libelle_source,
                    m.avertissement or "",
                    " ".join(f"{x:.2f},{y:.2f}" for x, y in m.points),
                ])
                lignes += 1
        journal.info("Export CSV : %s (%d mesures)", chemin, lignes)
        return lignes

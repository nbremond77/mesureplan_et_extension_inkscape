#!/usr/bin/env python3
"""Extension Inkscape « Mesure de plan » : échelle, calibration et métré à l'échelle.

Un seul script, plusieurs entrées de menu (fichiers .inx) qui le pilotent
par le paramètre --action :
  echelle   : définit ou lit l'échelle du cartouche ;
  calibrer  : corrige l'échelle à partir d'un trait tracé sur une cote connue ;
  mesurer   : mesure les objets sélectionnés et pose des étiquettes.

Compatible Inkscape 1.2 et suivants.
"""

from __future__ import annotations

import csv
import getpass
import json
import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import inkex
from lxml import etree

import mesureplan_calcul as calc

DOSSIER = Path(__file__).resolve().parent
ID_DONNEES = "mesureplan-echelle"
NOM_CALQUE = "Mesures"
journal = logging.getLogger("mesureplan")


# ---------------------------------------------------------------------------
# Configuration et journalisation
# ---------------------------------------------------------------------------

def charger_config() -> dict:
    """Lit mesureplan_config.json placé à côté du script."""
    chemin = DOSSIER / "mesureplan_config.json"
    with chemin.open(encoding="utf-8") as flux:
        return json.load(flux)


class FiltreUtilisateur(logging.Filter):
    """Ajoute l'utilisateur système à chaque enregistrement."""

    def __init__(self) -> None:
        super().__init__()
        try:
            self.utilisateur = getpass.getuser()
        except Exception:  # noqa: BLE001
            self.utilisateur = "inconnu"

    def filter(self, record: logging.LogRecord) -> bool:
        record.utilisateur = self.utilisateur
        return True


def configurer_journal(cfg: dict) -> None:
    """Console + fichier tournant.

    Particularité Inkscape : tout ce qui sort sur stderr s'affiche dans une
    fenêtre d'alerte. La console est donc réglée séparément (ERROR par défaut).
    """
    if journal.handlers:
        return
    format_ = logging.Formatter("%(asctime)s | %(levelname)-8s | %(utilisateur)s | %(module)s | %(message)s",
                                "%Y-%m-%d %H:%M:%S")
    filtre = FiltreUtilisateur()
    journal.setLevel(getattr(logging, cfg.get("niveau", "INFO").upper(), logging.INFO))
    journal.propagate = False

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(getattr(logging, cfg.get("niveau_console", "ERROR").upper(), logging.ERROR))
    gestionnaires = [console]
    try:
        fichier = Path(cfg.get("fichier", "logs/mesureplan.log")).expanduser()
        if not fichier.is_absolute():
            fichier = DOSSIER / fichier
        fichier.parent.mkdir(parents=True, exist_ok=True)
        gestionnaires.append(RotatingFileHandler(fichier, maxBytes=int(cfg.get("taille_max_octets", 524288)),
                                                 backupCount=int(cfg.get("nombre_sauvegardes", 3)),
                                                 encoding="utf-8"))
    except OSError:
        pass  # dossier d'extensions en lecture seule : journal console seulement
    for g in gestionnaires:
        g.setFormatter(format_)
        g.addFilter(filtre)
        journal.addHandler(g)


# ---------------------------------------------------------------------------
# Extension
# ---------------------------------------------------------------------------

class MesurePlan(inkex.EffectExtension):
    """Point d'entrée commun à toutes les entrées de menu."""

    def add_arguments(self, pars) -> None:
        pars.add_argument("--onglet", default="")
        pars.add_argument("--action", default="mesurer", choices=["echelle", "calibrer", "mesurer"])
        # Échelle
        pars.add_argument("--source", default="saisie", choices=["saisie", "lire"])
        pars.add_argument("--denominateur", type=float, default=100.0)
        pars.add_argument("--reinitialiser", type=inkex.Boolean, default=False)
        # Calibration
        pars.add_argument("--longueur", type=float, default=1.0)
        pars.add_argument("--unite_saisie", default="m", choices=["m", "cm", "mm"])
        pars.add_argument("--mode_reference", default="remplacer", choices=["remplacer", "ajouter"])
        pars.add_argument("--marquer_reference", type=inkex.Boolean, default=True)
        # Mesure
        pars.add_argument("--mode", default="auto", choices=["auto", "longueur", "surface", "angle"])
        pars.add_argument("--unite", default="config")
        pars.add_argument("--decimales", type=int, default=-1)
        pars.add_argument("--etiquettes", type=inkex.Boolean, default=True)
        pars.add_argument("--fichier_csv", default="")
        pars.add_argument("--rapide", type=inkex.Boolean, default=False)

    # ------------------------------------------------------------------
    def effect(self) -> None:
        self.cfg = charger_config()
        configurer_journal(self.cfg.get("journalisation", {}))
        aff = self.cfg.get("affichage", {})
        unite = aff.get("unite", "m") if self.options.unite == "config" else self.options.unite
        decimales = self.options.decimales if self.options.decimales >= 0 else int(aff.get("decimales", {}).get(unite, 2))
        self.fmt = calc.Formateur(unite, decimales, int(aff.get("decimales_surface", 2)),
                                  int(aff.get("decimales_angle", 1)))
        try:
            self.echelle = self._lire_echelle()
            {"echelle": self.action_echelle, "calibrer": self.action_calibrer,
             "mesurer": self.action_mesurer}[self.options.action]()
        except ErreurUtilisateur as erreur:
            inkex.errormsg(str(erreur))
        except Exception:
            journal.exception("Erreur inattendue (action %s)", self.options.action)
            raise

    # ------------------------------------------------------------------
    # Stockage de l'échelle dans le document
    # ------------------------------------------------------------------
    def _mm_par_uu(self) -> float:
        racine = self.svg
        return calc.mm_papier_par_uu(racine.get("width"), racine.get("viewBox"))

    def _lire_echelle(self) -> calc.EchelleDocument:
        element = self.svg.getElementById(ID_DONNEES)
        texte = element.text if element is not None else None
        defaut = float(self.cfg.get("echelle", {}).get("denominateur_defaut", 100))
        return calc.EchelleDocument.depuis_json(texte, self._mm_par_uu(), defaut)

    def _enregistrer_echelle(self) -> None:
        element = self.svg.getElementById(ID_DONNEES)
        if element is None:
            # Élément <metadata> : conservé par Inkscape, invisible au rendu
            element = etree.SubElement(self.svg, inkex.addNS("metadata", "svg"))
            element.set("id", ID_DONNEES)
        element.text = self.echelle.vers_json()

    # ------------------------------------------------------------------
    # Action : échelle du cartouche
    # ------------------------------------------------------------------
    def action_echelle(self) -> None:
        if self.options.source == "lire":
            textes = ["".join(t.itertext()) for t in self.svg.iter(inkex.addNS("text", "svg"))]
            trouve = calc.detecter_echelle("\n".join(textes))
            if trouve is None:
                raise ErreurUtilisateur(
                    "Aucune mention d'échelle (« Échelle 1/100 », « Ech. 1:50 »…) trouvée dans les textes du "
                    "plan.\nSi l'import PDF a converti le texte en tracés, saisissez l'échelle manuellement.")
            self.echelle.denominateur, self.echelle.origine = trouve, "lue sur le plan"
        else:
            if self.options.denominateur <= 0:
                raise ErreurUtilisateur("Le dénominateur d'échelle doit être positif.")
            self.echelle.denominateur, self.echelle.origine = self.options.denominateur, "saisie"
        if self.options.reinitialiser:
            self.echelle.references.clear()
        self._enregistrer_echelle()
        journal.info("Échelle cartouche %s (%s)", calc.texte_echelle(self.echelle.denominateur), self.echelle.origine)
        inkex.errormsg(self.echelle.synthese(self.fmt))

    # ------------------------------------------------------------------
    # Action : calibration
    # ------------------------------------------------------------------
    def action_calibrer(self) -> None:
        objets = self._objets_selectionnes()
        if len(objets) != 1:
            raise ErreurUtilisateur("Calibration : sélectionnez UN seul trait tracé d'une extrémité à l'autre "
                                    "d'une cote connue (outil Plume, accrochage aux nœuds activé).")
        element, sous_chemins = objets[0]
        sc = sous_chemins[0]
        longueur_uu = calc.longueur(sc.polyligne, sc.ferme)
        if longueur_uu <= 0:
            raise ErreurUtilisateur("Le trait sélectionné a une longueur nulle.")
        longueur_m = self.options.longueur / calc.FACTEURS_AFFICHAGE[self.options.unite_saisie]
        avant = longueur_uu * self.echelle.facteur_cartouche
        self.echelle.ajouter_reference(longueur_uu, longueur_m, self.options.mode_reference == "remplacer")
        self._enregistrer_echelle()

        if self.options.marquer_reference:
            # Trait de référence repérable : vert pointillé, renommé
            element.set("style", f"fill:none;stroke:{self.cfg['affichage'].get('couleur_reference', '#2E9E4F')};"
                                 f"stroke-width:{0.35 / self.echelle.mm_par_uu:.4f};stroke-dasharray:"
                                 f"{2 / self.echelle.mm_par_uu:.3f},{1 / self.echelle.mm_par_uu:.3f}")
            element.set(inkex.addNS("label", "inkscape"), f"Référence {self.fmt.longueur(longueur_m)}")
        avertissement = ""
        if len(sous_chemins) > 1 or len(sc.noeuds) > 2:
            avertissement = "\n⚠ Le trait comporte plus de deux nœuds : sa longueur totale a été utilisée."
        journal.info("Calibration : %.4f uu = %.4f m → 1:%.2f", longueur_uu, longueur_m,
                     self.echelle.denominateur_effectif)
        inkex.errormsg(f"Longueur au cartouche {calc.texte_echelle(self.echelle.denominateur)} : "
                       f"{self.fmt.longueur(avant)}\nCote réelle saisie : {self.fmt.longueur(longueur_m)}\n\n"
                       f"{self.echelle.synthese(self.fmt)}{avertissement}")

    # ------------------------------------------------------------------
    # Action : mesure
    # ------------------------------------------------------------------
    def action_mesurer(self) -> None:
        objets = self._objets_selectionnes()
        if not objets:
            raise ErreurUtilisateur("Sélectionnez un ou plusieurs tracés à mesurer.\n"
                                    "Astuce : Ctrl+clic sélectionne un objet à l'intérieur d'un groupe.")
        f = self.echelle.facteur
        resultats: list[dict] = []
        droites: list[tuple[calc.Point, calc.Point]] = []

        for element, sous_chemins in objets:
            nom = element.get(inkex.addNS("label", "inkscape")) or element.get("id")
            for sc in sous_chemins:
                r = {"objet": nom, "type": "", "longueur_m": None, "surface_m2": None,
                     "perimetre_m": None, "angle_deg": None}
                mode = self.options.mode
                if mode == "angle":
                    if len(sc.noeuds) == 3 and not sc.ferme:
                        a, s, b = sc.noeuds
                        r.update(type="angle", angle_deg=calc.angle_sommet(a, s, b))
                        # Étiquette décalée sur la bissectrice pour ne pas masquer le sommet
                        position = calc.point_bissectrice(a, s, b, 4.0 / self.echelle.mm_par_uu)
                    elif len(sc.noeuds) == 2:
                        droites.append((sc.noeuds[0], sc.noeuds[1]))
                        continue
                    else:
                        raise ErreurUtilisateur("Angle : sélectionnez un tracé de 3 nœuds (bras – sommet – bras) "
                                                "ou deux traits de 2 nœuds.")
                elif (sc.ferme and mode != "longueur") or mode == "surface":
                    poly = sc.polyligne
                    r.update(type="surface", surface_m2=calc.aire(poly) * f * f,
                             perimetre_m=calc.longueur(poly, True) * f)
                    position = calc.centroide(poly)
                else:
                    longueur_m = calc.longueur(sc.polyligne, sc.ferme) * f
                    nature = "distance" if len(sc.noeuds) == 2 and sc.rectiligne else "chaîne"
                    r.update(type=nature, longueur_m=longueur_m)
                    if len(sc.noeuds) == 2:
                        droites.append((sc.noeuds[0], sc.noeuds[1]))
                    k = (len(sc.polyligne) - 1) // 2
                    position = ((sc.polyligne[k][0] + sc.polyligne[k + 1][0]) / 2,
                                (sc.polyligne[k][1] + sc.polyligne[k + 1][1]) / 2) if len(sc.polyligne) > 1 \
                        else sc.polyligne[0]
                r["texte"] = self._texte_resultat(r)
                resultats.append(r)
                if self.options.etiquettes:
                    self._poser_etiquette(r["texte"], position)

        # Angle entre deux traits droits
        if self.options.mode == "angle" or (self.options.mode == "auto" and len(droites) == 2 and len(objets) == 2):
            if len(droites) == 2:
                aigu = calc.angle_entre_droites(*droites[0], *droites[1])
                r = {"objet": "2 traits", "type": "angle", "angle_deg": aigu, "longueur_m": None,
                     "surface_m2": None, "perimetre_m": None}
                r["texte"] = f"{self.fmt.angle(aigu)} / {self.fmt.angle(180 - aigu)}"
                resultats.append(r)
                if self.options.etiquettes and self.options.mode == "angle":
                    self._poser_etiquette(r["texte"], calc.intersection_droites(*droites[0], *droites[1]))
            elif self.options.mode == "angle" and droites:
                raise ErreurUtilisateur("Angle : il faut exactement deux traits de 2 nœuds.")

        if self.options.fichier_csv:
            self._exporter_csv(resultats)
        journal.info("%d mesure(s) — échelle 1:%.2f", len(resultats), self.echelle.denominateur_effectif)

        # Résumé : systématique en mode complet, seulement si utile en mode rapide
        afficher = (not self.options.rapide or len(resultats) > 1
                    or self.cfg.get("affichage", {}).get("resume_en_mode_rapide", False)
                    or not self.options.etiquettes)
        if afficher:
            inkex.errormsg(self._resume(resultats))

    def _texte_resultat(self, r: dict) -> str:
        if r["type"] == "surface":
            return f"{self.fmt.surface(r['surface_m2'])}\nP {self.fmt.longueur(r['perimetre_m'])}"
        if r["type"] == "angle":
            return self.fmt.angle(r["angle_deg"])
        prefixe = "Σ " if r["type"] == "chaîne" else ""
        return prefixe + self.fmt.longueur(r["longueur_m"])

    def _resume(self, resultats: list[dict]) -> str:
        lignes = [f"• {r['objet']} ({r['type']}) : {r['texte'].replace(chr(10), ' – ')}" for r in resultats]
        surfaces = [r["surface_m2"] for r in resultats if r["surface_m2"] is not None]
        longueurs = [r["longueur_m"] for r in resultats if r["longueur_m"] is not None]
        if len(surfaces) > 1:
            lignes.append(f"Σ surfaces : {self.fmt.surface(sum(surfaces))}")
        if len(longueurs) > 1:
            lignes.append(f"Σ longueurs : {self.fmt.longueur(sum(longueurs))}")
        return "\n".join(lignes) + "\n\n" + self.echelle.synthese(self.fmt)

    # ------------------------------------------------------------------
    # Outils internes
    # ------------------------------------------------------------------
    def _objets_selectionnes(self) -> list[tuple[inkex.BaseElement, list[calc.SousChemin]]]:
        """Tracés sélectionnés convertis en sous-chemins aplatis (coordonnées racine)."""
        objets = []
        groupes = 0
        for element in self.svg.selection.values():
            if isinstance(element, inkex.Group):
                groupes += 1
                continue
            if isinstance(element, (inkex.TextElement, inkex.Image)) or not isinstance(element, inkex.ShapeElement):
                continue
            try:
                chemin = element.path.to_absolute()
            except Exception:  # noqa: BLE001 — objet sans géométrie de tracé (clone, etc.)
                journal.warning("Objet ignoré (pas de tracé) : %s", element.get("id"))
                continue
            # Repère « fermé » par sous-chemin : un Z termine le sous-chemin courant
            fermes: list[bool] = []
            for commande in chemin:
                if commande.letter in "Mm":
                    fermes.append(False)
                elif commande.letter in "Zz" and fermes:
                    fermes[-1] = True
            chemin = chemin.transform(element.composed_transform())
            superchemin = [[[list(p) for p in noeud] for noeud in sous] for sous in chemin.to_superpath()]
            sous_chemins = calc.aplatir(superchemin, fermes)
            if sous_chemins:
                objets.append((element, sous_chemins))
        if groupes and not objets:
            raise ErreurUtilisateur(f"{groupes} groupe(s) sélectionné(s) : les groupes ne sont pas mesurés.\n"
                                    "Ctrl+clic pour sélectionner un tracé à l'intérieur d'un groupe, "
                                    "ou tracez votre propre ligne avec l'outil Plume.")
        return objets

    def _calque_mesures(self) -> inkex.Layer:
        for calque in self.svg.findall("svg:g"):
            if calque.get(inkex.addNS("groupmode", "inkscape")) == "layer" \
                    and calque.get(inkex.addNS("label", "inkscape")) == NOM_CALQUE:
                return calque
        calque = inkex.Layer.new(NOM_CALQUE)
        self.svg.append(calque)
        return calque

    def _poser_etiquette(self, texte: str, position: calc.Point) -> None:
        aff = self.cfg.get("affichage", {})
        taille = float(aff.get("taille_police_mm", 2.5)) / self.echelle.mm_par_uu  # mm papier → uu
        couleur = aff.get("couleur_etiquettes", "#C0392B")
        lignes = texte.split("\n")
        x, y = position
        y -= taille * (len(lignes) - 1) * 0.6  # centrage vertical approximatif du bloc
        element = inkex.TextElement()
        element.set("x", f"{x:.4f}")
        element.set("y", f"{y:.4f}")
        element.set("style", f"font-size:{taille:.4f}px;font-family:sans-serif;font-weight:bold;"
                             f"text-anchor:middle;fill:{couleur};stroke:#ffffff;"
                             f"stroke-width:{taille * 0.18:.4f}px;paint-order:stroke;stroke-linejoin:round")
        element.set(inkex.addNS("label", "inkscape"), f"Mesure {texte.splitlines()[0]}")
        for i, ligne in enumerate(lignes):
            tspan = inkex.Tspan()
            tspan.text = ligne
            tspan.set("x", f"{x:.4f}")
            tspan.set("y", f"{y + i * taille * 1.2:.4f}")
            tspan.set(inkex.addNS("role", "sodipodi"), "line")
            element.append(tspan)
        self._calque_mesures().append(element)

    def _exporter_csv(self, resultats: list[dict]) -> None:
        chemin = Path(self.options.fichier_csv).expanduser()
        nouveau = not chemin.exists()
        nombre = lambda v, d=4: "" if v is None else f"{v:.{d}f}".replace(".", ",")  # noqa: E731
        try:
            with chemin.open("a", encoding="utf-8-sig" if nouveau else "utf-8", newline="") as flux:
                ecrivain = csv.writer(flux, delimiter=";")
                if nouveau:
                    ecrivain.writerow(["Date", "Document", "Objet", "Type", "Longueur (m)", "Surface (m²)",
                                       "Périmètre (m)", "Angle (°)", "Échelle (1:N)"])
                for r in resultats:
                    ecrivain.writerow([datetime.now().isoformat(timespec="seconds"),
                                       self.svg.get(inkex.addNS("docname", "sodipodi"), ""),
                                       r["objet"], r["type"], nombre(r["longueur_m"]), nombre(r["surface_m2"]),
                                       nombre(r["perimetre_m"]), nombre(r["angle_deg"], 2),
                                       nombre(self.echelle.denominateur_effectif, 2)])
        except OSError as erreur:
            journal.exception("Écriture CSV impossible : %s", chemin)
            raise ErreurUtilisateur(f"Écriture du CSV impossible : {erreur}") from erreur


class ErreurUtilisateur(Exception):
    """Erreur d'utilisation : message affiché tel quel, sans trace technique."""


if __name__ == "__main__":
    MesurePlan().run()

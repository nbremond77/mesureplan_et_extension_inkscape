// Gabarit commun aux documents MesurePlan (Typst ≥ 0.12).
// Polices : Inter (titres et texte), DejaVu Sans Mono (code) — repli automatique sur DejaVu Sans.

#let bleu = rgb("#1F77D0")
#let orange = rgb("#E4572E")
#let gris = rgb("#5A6270")
#let fond-encadre = rgb("#F4F6F8")

#let gabarit(titre: "", sous-titre: "", version: "", date: "", corps) = {
  set document(title: titre, author: "Bernard")
  set page(
    paper: "a4",
    margin: (top: 2.4cm, bottom: 2.2cm, left: 2.2cm, right: 2.2cm),
    header: context {
      if counter(page).get().first() > 1 [
        #set text(8pt, fill: gris)
        #titre #h(1fr) MesurePlan #version
        #v(-6pt)
        #line(length: 100%, stroke: 0.4pt + gris)
      ]
    },
    footer: context [
      #set text(8pt, fill: gris)
      #date #h(1fr) #counter(page).display("1 / 1", both: true)
    ],
  )
  set text(font: ("Inter", "DejaVu Sans", "Liberation Sans"), size: 10pt, lang: "fr", region: "FR")
  set par(justify: true, leading: 0.62em)
  set heading(numbering: "1.1")
  show heading.where(level: 1): it => {
    pagebreak(weak: true)
    set text(17pt, fill: bleu, weight: "bold")
    block(below: 0.9em, it)
  }
  show heading.where(level: 2): it => {
    set text(12.5pt, fill: bleu.darken(15%), weight: "bold")
    block(above: 1.3em, below: 0.7em, it)
  }
  show heading.where(level: 3): set text(10.5pt, weight: "bold")
  show raw: set text(font: ("DejaVu Sans Mono", "Liberation Mono"), size: 8.6pt)
  show raw.where(block: true): it => block(fill: fond-encadre, inset: 8pt, radius: 3pt, width: 100%, it)
  show link: set text(fill: bleu)
  set table(stroke: 0.4pt + rgb("#C9CED6"), inset: 5pt)
  show table.cell.where(y: 0): set text(weight: "bold")

  // --- Page de titre
  v(4.5cm)
  block(text(28pt, weight: "bold", fill: bleu, titre))
  v(0.3cm)
  block(text(14pt, fill: gris, sous-titre))
  v(1.2cm)
  line(length: 40%, stroke: 2pt + orange)
  v(0.6cm)
  text(11pt)[Version #version — #date]
  v(1fr)
  text(9pt, fill: gris)[Application MesurePlan — métré, annotation et impression à l'échelle de plans PDF vectoriels. \
    Licence AGPL-3.0 (imposée par PyMuPDF).]
  pagebreak()
  outline(indent: auto, depth: 2)
  pagebreak()
  corps
}

// Encadré coloré (note, attention, conseil)
#let encadre(titre: "Note", couleur: bleu, corps) = block(
  fill: couleur.lighten(88%), stroke: (left: 3pt + couleur), inset: (x: 10pt, y: 8pt),
  radius: (right: 3pt), width: 100%, above: 1em, below: 1em,
)[#text(weight: "bold", fill: couleur.darken(20%), titre) \ #corps]

#let attention(corps) = encadre(titre: "Attention", couleur: orange, corps)
#let conseil(corps) = encadre(titre: "Conseil", couleur: rgb("#2E9E4F"), corps)

// Touche de clavier
#let touche(t) = box(
  fill: white, stroke: 0.6pt + gris, radius: 2pt, inset: (x: 3pt, y: 1.5pt), baseline: 20%,
  text(8.5pt, font: ("DejaVu Sans Mono", "Liberation Mono"), t),
)

// Boîte de schéma d'architecture
#let module(nom, detail, couleur: bleu) = rect(
  width: 100%, fill: couleur.lighten(85%), stroke: 0.8pt + couleur, radius: 3pt, inset: 6pt,
)[#text(weight: "bold", size: 8.5pt, nom) \ #text(size: 7.5pt, fill: gris, detail)]

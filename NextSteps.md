# Next Steps: Weiterentwicklung des Semantic Evaluation Frameworks

## Ausgangslage

Die erste vollständige Qualifikationsmatrix für die semantische Rollenklassifikation wurde erfolgreich ausgeführt. Obwohl kein Kandidat die definierten Qualitätsgrenzen erreicht hat, liefert die Evaluation wertvolle Erkenntnisse über das eigentliche Problem.

Die Ergebnisse deuten darauf hin, dass die Leistungsfähigkeit der verwendeten LLMs derzeit nicht der dominierende limitierende Faktor ist. Stattdessen zeigen sich Schwächen im zugrunde liegenden Domänenmodell und im Aufbau des Goldstandards.

Diese Erkenntnis verschiebt den Schwerpunkt der weiteren Arbeiten von der Optimierung einzelner Modelle hin zur Weiterentwicklung des semantischen Modells selbst.

## Erkenntnis 1: Der Goldstandard ist nicht unabhängig

Der aktuelle Goldstandard wurde aus einem automatisch erzeugten Proposal erstellt, das anschließend im Human-in-the-Loop-Verfahren überprüft wurde.

Der Reviewprozess ist dadurch zwangsläufig vom ursprünglichen Proposal beeinflusst.

Besonders kritisch ist dies bei:

* mehrdeutigen semantischen Rollen,
* Klauseln mit mehreren gleichzeitig gültigen Rollen,
* Fällen, in denen eine vollständige Analyse zeitaufwändig wäre.

In solchen Situationen besteht eine natürliche Tendenz, ein plausibles Proposal zu übernehmen, anstatt sämtliche Alternativen vollständig neu zu bewerten.

Dadurch entsteht ein sogenannter Anchoring-Effekt: Der Goldstandard beschreibt nicht ausschließlich die menschliche Interpretation einer Klausel, sondern teilweise auch die Interpretation des ursprünglichen Modells.

Für Regressionstests und Promptvergleiche bleibt dieser Goldstandard dennoch wertvoll, da alle Kandidaten gegen denselben Maßstab bewertet werden. Für wissenschaftliche Aussagen über die "richtige" Klassifikation muss dieser Einfluss jedoch berücksichtigt werden.

## Erkenntnis 2: Wir vermischen verschiedene Ebenen der Semantik

Die Diskussion hat gezeigt, dass bisher unterschiedliche Arten von Bedeutung in einer einzigen Rollenliste zusammengefasst werden.

Insbesondere lassen sich mindestens zwei voneinander unabhängige Ebenen unterscheiden.

### Sprachliche Funktion einer Klausel

Sie beschreibt, was eine Aussage sprachlich tut.

Beispiele:

* Requirement
* Recommendation
* Permission
* Definition
* Explanation
* Rationale
* Example

Diese Eigenschaften ergeben sich hauptsächlich aus dem Wortlaut der Klausel.

### Strukturelle Funktion innerhalb der Norm

Sie beschreibt, welche Aufgabe eine Klausel innerhalb der Gesamtstruktur der Norm erfüllt.

Beispiele:

* Scope
* Terminology
* System Requirements
* Verification
* Validation
* Configuration Management
* Documentation

Diese Eigenschaften ergeben sich überwiegend aus der Position der Klausel innerhalb der Dokumentstruktur.

Eine Klausel kann gleichzeitig sprachlich ein Requirement sein und strukturell zum Kapitel "Verification" gehören.

Diese beiden Aussagen widersprechen sich nicht.

## Erkenntnis 3: Die Dokumentstruktur dominiert die Interpretation

Die Evaluation legt nahe, dass die strukturelle Position einer Klausel wesentlich stärker zur Bestimmung ihrer Funktion beiträgt als ihre sprachliche Formulierung.

Dies erklärt insbesondere den Erfolg des "structure-aware"-Prompts.

Die Dokumentstruktur enthält Informationen, die im reinen Klauseltext nicht enthalten sind.

Für technische Normen ist diese Struktur nicht zufällig, sondern folgt klar definierten Konventionen.

## Erkenntnis 4: Die strukturellen Rollen sollten neu modelliert werden

Statt einer flachen Liste semantischer Rollen sollte zunächst ein strukturelles Referenzmodell entwickelt werden.

Dabei wird zwischen einer allgemeinen und einer domänenspezifischen Ebene unterschieden.

### Kanonische Dokumentstruktur

Als Grundlage dienen die ISO/IEC Directives, Part 2.

Sie definieren einen weitgehend domänenunabhängigen Aufbau technischer Normen.

Beispielsweise:

* Dokumentmetadaten
* Scope
* Normative References
* Terms and Definitions
* Normativer Hauptteil
* Verification
* Management
* Annexes

Diese Struktur bildet den gemeinsamen Kern aller Wissensdomänen.

### Domänenspezifische Struktur

Für Functional Safety wird dieser Kern um die Phasen des Sicherheitslebenszyklus erweitert.

Beispielsweise:

* Hazard Analysis
* Safety Goals
* System Requirements
* Hardware Requirements
* Software Requirements
* Architecture
* Integration
* Verification
* Validation
* Operation
* Maintenance

Diese Ebene beschreibt die funktionale Einordnung einer Klausel innerhalb des V-Modells.

## Konsequenz für den Standards Atlas

Die strukturelle Klassifikation sollte zukünftig nicht mehr als einfache Rollenliste verstanden werden.

Stattdessen sollte jede Klausel ein strukturelles Profil besitzen, das mehrere voneinander unabhängige Dimensionen beschreibt.

Dieses Profil bildet die Grundlage für spätere Beziehungen zwischen Normen unterschiedlicher Domänen.

Gerade diese strukturelle Vergleichbarkeit ist eines der langfristigen Ziele des Standards Atlas.

## Priorisierte nächste Arbeitsschritte

### 1. Strukturelles Referenzmodell entwickeln

Definition einer kanonischen Struktur auf Basis der ISO/IEC Directives Part 2.

### 2. Functional-Safety-Struktur ableiten

Abbildung des Sicherheitslebenszyklus und des V-Modells auf dieses Referenzmodell.

### 3. Rollenmodell überarbeiten

Ersetzen der bisherigen flachen Rollenliste durch ein mehrdimensionales Strukturmodell.

### 4. Goldstandard überprüfen

Analyse, welche Rollen überwiegend strukturell bestimmt werden und welche tatsächlich aus dem Klauselinhalt hervorgehen.

### 5. Evaluationsmetriken erweitern

Die zukünftige Evaluation sollte strukturelle Rollen, sprachliche Funktionen und weitere semantische Dimensionen getrennt bewerten.

## Langfristige Forschungsfrage

Die bisherigen Ergebnisse deuten darauf hin, dass die eigentliche Herausforderung nicht in der Auswahl des leistungsfähigsten LLM liegt.

Die zentrale Forschungsfrage lautet vielmehr:

**Wie lässt sich die Bedeutung technischer Normen so modellieren, dass Beziehungen zwischen unterschiedlichen Standards zuverlässig erkannt und erklärt werden können?**

Die Entwicklung eines tragfähigen semantischen Domänenmodells ist damit zu einer zentralen Aufgabe des Standards Atlas geworden. Die LLM-Evaluation dient künftig primär dazu, die Eignung verschiedener Modelle zur Rekonstruktion dieses Domänenmodells zu untersuchen und nicht lediglich deren Übereinstimmung mit einem einzelnen, historisch gewachsenen Goldstandard zu messen.


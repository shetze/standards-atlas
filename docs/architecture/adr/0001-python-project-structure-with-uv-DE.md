i# ADR 0001: Python-Projektstruktur mit uv und src-Layout

## Status

Proposed

## Kontext

Standards Atlas ist historisch als Sammlung von Skripten, Datenverzeichnissen und experimentellen Werkzeugen gewachsen. Die bestehende Struktur erfüllt ihren Zweck, erschwert aber zunehmend Wartung, Erweiterung und Wiederverwendung.

Insbesondere bestehen aktuell folgende Probleme:

* Die fachliche Logik ist mit Kommandozeilen-Skripten, Dateiformaten und Tool-spezifischer Verarbeitung vermischt.
* Die Importpfade hängen teilweise vom aktuellen Arbeitsverzeichnis ab.
* Es gibt keinen einheitlichen Python-Projektstandard.
* Abhängigkeiten sind nicht zentral und reproduzierbar beschrieben.
* Tests, CLI, spätere REST API und Adapter für Doorstop oder BASIL können nicht sauber auf einen gemeinsamen Kern zugreifen.
* Neue Funktionen erhöhen das Risiko, bestehende Skripte weiter zu verflechten.

Gleichzeitig soll Standards Atlas künftig nicht nur ein Skriptwerkzeug bleiben, sondern zu einer modularen Plattform für Standards, semantische Beziehungen und Traceability weiterentwickelt werden.

## Entscheidung

Standards Atlas wird schrittweise in ein reguläres Python-Projekt überführt.

Dafür verwenden wir:

* `uv` als Werkzeug für Dependency Management, virtuelle Umgebung und reproduzierbare Installation.
* `pyproject.toml` als zentrale Projektbeschreibung.
* ein `src/`-Layout für den produktiven Python-Code.
* ein Paket `standards_atlas` als gemeinsamen Kern für CLI, Adapter, Tests und spätere APIs.

Die Zielstruktur beginnt mit:

```text
standards-atlas/
  pyproject.toml
  uv.lock
  README.md

  src/
    standards_atlas/
      __init__.py
      __main__.py
      cli.py

  tests/
  docs/
    architecture/
      adr/
```

Bestehende Skripte unter `tools/` bleiben zunächst unverändert funktionsfähig. Die Migration erfolgt anschließend schrittweise in kleinen, überprüfbaren Änderungen.

## Begründung

`uv` wird verwendet, weil es schnelle und reproduzierbare Python-Umgebungen ermöglicht und moderne Python-Projektstandards direkt unterstützt. Es ersetzt in diesem Projekt die bisherige implizite Verwaltung von Abhängigkeiten.

Das `src/`-Layout verhindert, dass Python versehentlich lokale Dateien aus dem Projektwurzelverzeichnis importiert. Dadurch werden Importprobleme früher sichtbar und Tests laufen näher an der später installierten Paketstruktur.

Das Paket `standards_atlas` schafft eine stabile technische Mitte. CLI, Doorstop-Adapter, BASIL-Adapter, IntelliDoc-Funktionalität, Tests und spätere REST-Schnittstellen sollen künftig nicht mehr jeweils eigene Logik enthalten, sondern auf denselben Kern zugreifen.

Diese Entscheidung verändert zunächst keine fachliche Funktionalität. Sie schafft lediglich die Grundlage, um die bestehende Logik kontrolliert zu entflechten.

## Konsequenzen

Positive Konsequenzen:

* Abhängigkeiten werden zentral in `pyproject.toml` gepflegt.
* Das Projekt kann lokal reproduzierbar mit `uv` installiert und ausgeführt werden.
* Tests können künftig stabile Imports verwenden.
* Neue Module können unterhalb von `src/standards_atlas/` sauber strukturiert werden.
* Die Migration kann inkrementell erfolgen, ohne bestehende Skripte sofort umzubauen.

Negative Konsequenzen:

* Entwicklerinnen und Entwickler benötigen künftig `uv` oder müssen die `pyproject.toml`-Struktur mit alternativen Werkzeugen verstehen.
* Bestehende Skripte müssen später auf neue Importpfade umgestellt werden.
* Für eine Übergangszeit existieren alte und neue Struktur parallel.
* Die Projektstruktur wird kurzfristig größer, bevor sie einfacher wird.

## Alternativen

### Poetry

Poetry hätte ebenfalls Dependency Management und Packaging bereitgestellt. Es wurde nicht gewählt, weil `uv` einfacher, schneller und näher an aktuellen Python-Standards wie PEP 621 arbeitet.

### Reines pip/requirements.txt

Ein klassisches `requirements.txt` wäre einfacher, bietet aber weniger Projektstruktur und keine zentrale Beschreibung von Paket, CLI-Einstiegspunkten und Entwicklungsabhängigkeiten.

### Keine Umstrukturierung

Die bestehende Skriptstruktur könnte beibehalten werden. Das würde kurzfristig Aufwand sparen, würde aber die weitere Entwicklung von Traceability API, Doorstop-Adapter, BASIL-Adapter und Tests deutlich erschweren.

## Umsetzung

PR 1 führt nur die Projektgrundlage ein:

1. `pyproject.toml` anlegen.
2. `uv.lock` erzeugen.
3. `src/standards_atlas/` anlegen.
4. minimale CLI bereitstellen.
5. `tests/` anlegen.
6. ADR-Verzeichnis unter `docs/architecture/adr/` anlegen.
7. bestehende Skripte unverändert lassen.

Beispielaufrufe:

```bash
uv sync
uv run standards-atlas --help
uv run python -m standards_atlas
uv run pytest
```

## Entscheidungsdatum

2026-07-07


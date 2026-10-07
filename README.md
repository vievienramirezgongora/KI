# Modulare Ausreißererkennung

Python **3.10 oder neuer**, ohne externe Abhängigkeiten. CSV und JSON werden
einmal extrahiert; Tukey, Z-Score und Modified Z-Score analysieren dieselbe
unveränderliche Zahlenfolge. Es werden keine Daten entfernt oder überschrieben.

## Start

Im Repository-Verzeichnis:

```bash
python3 -m outlier_detection --config config/pipeline.json
python3 -m outlier_detection --config config/pipeline.json --input examples/measurements.json --extractor json_measurements
python3 -m unittest discover -s tests -v
```

Beide Beispiele enthalten dieselben 13 Werte. Alle drei Verfahren markieren
Datensatz 13 mit dem Wert `100`. Die Ausgabe ist JSON mit allen Eingabewerten,
Flags, Scores, berechneten Kennzahlen, Ausreißern und Metadaten.
`record` zählt Datensätze ab 1, bei CSV ohne Kopfzeile. Es ist keine physische
Dateizeilennummer: Ein CSV-Datensatz kann mehrere Zeilen umfassen.

## Architektur und Single Source of Truth

```text
pipeline.json ──> Configuration ──> validierte Methoden-/Extraktor-Einstellungen
                       │
                  DocumentStore  <── gemeinsame Instanz für alle Dateizugriffe
                       │
                 CSV-/JSON-Extraktor
                       │
               eine Folge von Messwerten
                       │
              ┌────────┼───────────┐
            Tukey   Z-Score   Modified Z-Score
```

**Kein Detektor lädt Info-, Konfigurations- oder Datendateien.** Die zentrale
Konfigurationsauflösung übergibt jeder Factory ausschließlich deren Parameter.
Die Factory validiert diese und erstellt einen unveränderlich konfigurierten
Detektor. Die Pipeline übergibt seiner `detect()`-Methode nur Messwerte.
Metadaten fließen nur in den Ergebnisbericht ein.

- `config/pipeline.json` verknüpft Dateien und wählt den Extraktor.
- `config/methods.json` ist die einzige Quelle für konfigurierbare statistische
  Parameter. Im Anwendungscode gibt es dafür keine Ersatz- oder Standardwerte.
- `config/extractors.json` definiert Feldname, CSV-Trennzeichen, JSON-Pfad und
  Umgang mit fehlenden Werten. Mehrere benannte Extraktoren sind möglich.
- `examples/info.json` enthält die optionalen Metadaten; das Feld `metadata`
  darf in der Pipeline-Konfiguration entfallen.
- `DocumentStore` löst absolute Pfade und symbolische Links auf. Jede Datei
  wird pro Store höchstens einmal gelesen, JSON höchstens einmal geparst –
  auch bei mehrfachen Referenzen. JSON-Verbraucher erhalten unabhängige Kopien.

Der Cache gilt pro Pipeline-Instanz, ohne globalen Zustand. Wiederholte
`run()`-Aufrufe lesen bereits geladene Dateien nicht erneut. Für geänderte
Dateiinhalte eine neue Pipeline erstellen. Dies ist ein Cache beim ersten
Zugriff, kein atomarer Snapshot sämtlicher Dateien; Dateien während eines
Laufs deshalb nicht parallel bearbeiten. Verschiedene Pipeline-Instanzen
können bei Bedarf denselben `DocumentStore` erhalten. Hardlinks mit
unterschiedlichen Pfaden werden als unterschiedliche Dateien behandelt.

Pfade aus `pipeline.json` sind relativ zu dieser Konfigurationsdatei.
Der explizite CLI-Parameter `--input` ist relativ zum Arbeitsverzeichnis.
Alle Dateien verwenden UTF-8; ein UTF-8-BOM wird akzeptiert.

## Konkrete Parameter und Regeln

Die konkreten Werte stehen ausschließlich in
[`config/methods.json`](config/methods.json): `detectors` ordnet die Namen der
aktiven Verfahren ihren Einstellungen zu. `zero_spread` definiert die gemeinsame
Regel bei Streuung null. Die Pipeline führt genau die konfigurierten Verfahren
aus. Es gibt keine zweite Parameterliste oder Ersatzwerte im Anwendungscode.

| Methode | Berechnung | Ausreißerregel |
| --- | --- | --- |
| Tukey | `IQR = Q3 − Q1` | `x < Q1 − factor·IQR` oder `x > Q3 + factor·IQR` |
| Z-Score | `z = (x − Mittelwert) / Standardabweichung` | `abs(z) > threshold` |
| Modified Z-Score | `m = scale·(x − Median) / MAD` | `abs(m) > threshold` |

Tukey verwendet linear interpolierte Quartile mit Position `(n−1)·p`
(Hyndman–Fan Typ 7). MAD ist der Median der absoluten Abweichungen vom Median;
er wird nicht zusätzlich skaliert. `scale` entspricht näherungsweise
`Φ⁻¹(0.75)`. Bei Z-Score bedeutet `ddof=0` Populationsstandardabweichung,
`ddof=1` Stichprobenstandardabweichung. Werte genau auf einer Grenze gelten
nicht als Ausreißer. Jedes Verfahren entscheidet separat; es gibt keine
versteckte Zusammenführung der drei Entscheidungen.

Bei Standardabweichung oder MAD gleich null sind standardisierte Scores
undefiniert. `zero_spread="flag_deviations"` liefert dafür JSON `null` und
markiert nur vom jeweiligen Zentrum abweichende Werte. Damit wird z. B. bei
`[1,1,1,1,100]` trotz MAD=0 der Wert 100 markiert. Das ist eine ausdrücklich
gewählte Ersatzregel, kein berechneter Modified Z-Score. Mit
`zero_spread="error"` bricht der Lauf stattdessen ab. Tukey benötigt keine
Division und verwendet seine Grenzen auch bei IQR=0.

Bei `missing="error"` führen fehlende Felder, `null` und leere Zahlenfelder
zum Fehler. `missing="skip"` überspringt diese Datensätze und protokolliert
deren Nummern. Ungültige Zahlen, boolesche Werte, NaN, Infinity, fehlerhafte
CSV-Spaltenzahlen und leere Messreihen sind Fehler. Unbekannte oder fehlende
Konfigurationsschlüssel sowie doppelte JSON-Schlüssel werden abgewiesen.
Das Programm beendet fehlerhafte CLI-Aufrufe mit Exit-Code 2.

## Als Python-Modul verwenden

```python
from outlier_detection import Pipeline

pipeline = Pipeline("config/pipeline.json")
report = pipeline.run()
print(report["methods"]["tukey"]["outliers"])
```

## Open-Closed Principle und Separation of Concerns

`contracts.py` definiert die Erweiterungspunkte `Detector` und `Extractor`
als Python-Protokolle. Eine Vererbung von eingebauten Klassen ist nicht nötig.

Neue Verfahren oder Formate kommen in **neue Module**. Eine eigene Factory
validiert deren individuelle Einstellungen und erstellt die Implementierung:

- Detektor-Factory: `(settings, zero_spread) -> Detector`;
  der Detektor implementiert `detect(values) -> Detection`.
- Extraktor-Factory: `(settings) -> Extractor`;
  der Extraktor implementiert `extract(documents, path) -> Extraction`.

Eigene Registries werden bei der Erstellung übergeben. Im folgenden Beispiel
stehen `MyDetector` und `MyExtractor` für eigene Implementierungen:

```python
from outlier_detection import Pipeline
from outlier_detection.methods import DETECTORS
from outlier_detection.extractors import EXTRACTORS
from my_plugins import MyDetector, MyExtractor

pipeline = Pipeline(
    "config/pipeline.json",
    detector_factories={**DETECTORS, "my_detector": MyDetector.from_config},
    extractor_factories={**EXTRACTORS, "my_format": MyExtractor.from_config},
)
```

Die neue Methode wird unter `detectors.my_detector` in der Methoden-Konfiguration
eingetragen. Ein neuer benannter Extraktor erhält `kind: "my_format"` sowie
seine Parameter in der Extraktor-Konfiguration und wird in `input.extractor`
ausgewählt. `kind` wird zentral zur Auswahl verwendet; nur die verbleibenden
Parameter gehen an die Extraktor-Factory. Die eingebauten Registries sind
schreibgeschützt. Die neuen Registries gelten nur für diese Pipeline.

Pipeline, zentrale Konfigurationsauflösung und bestehende Implementierungen
werden bei dieser Erweiterung nicht geändert. Die generische CLI verwendet
die eingebauten Registries; eigene Plugins werden über einen eigenen Python-
Einstiegspunkt injiziert, nicht über dynamische Imports aus JSON.

Die Zuständigkeiten bleiben getrennt: `documents.py` übernimmt Dateizugriff
und Cache, `configuration.py` löst Referenzen auf und wählt Factories aus,
jede Implementierung validiert ihre eigenen Parameter, `extractors.py`
extrahiert Zahlen, `methods.py` berechnet Statistiken, `pipeline.py` steuert
den Ablauf, und `__main__.py` kümmert sich um die CLI.

Die Tests prüfen bekannte statistische Ergebnisse, Grenzfälle, CSV-/JSON-
Gleichheit, Eingabevalidierung und tatsächliche Dateileseaufrufe. Ein weiterer
Test verbietet Dateizugriffe während der Detektorausführung.
`tests/test_extensions.py` führt einen unabhängigen Detektor und ein weiteres
Dateiformat durch dieselbe Pipeline aus und prüft deren eigene Validierung.
Die Architekturvorgaben für spätere Änderungen stehen in `AGENTS.md`.

# Architekturvorgaben

- Open-Closed Principle: Neue Detektoren und Extraktoren über die vorhandenen
  Schnittstellen und injizierte Registries ergänzen. Die Pipeline und bestehende
  Implementierungen dürfen dafür keine zusätzlichen Fallunterscheidungen brauchen.
- Single Source of Truth: Konfigurierbare Werte ausschließlich aus den jeweiligen
  Konfigurationsdateien beziehen; keine duplizierten Defaults im Anwendungscode.
- Separation of Concerns: Dateizugriff, Konfigurationsauflösung, Extraktion,
  Statistik, Ablaufsteuerung und CLI getrennt halten.
- Konfigurations- und Metadaten-Dateien nur über den gemeinsamen DocumentStore
  lesen. Detektoren erhalten Daten und Parameter; sie führen keine Datei-I/O aus.
- Änderungen mit `python3 -m unittest discover -s tests -v` prüfen. Bei neuen
  Erweiterungspunkten auch eine externe Implementierung über die Pipeline testen.

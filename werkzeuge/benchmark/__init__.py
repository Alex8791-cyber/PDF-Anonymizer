"""Entwicklungs-Benchmark (Entwicklungskorpus) für den PDF-Anonymisierer.

Bausteine:
    generator.py       erzeugt deterministisch (Seed) realistische deutsche Versicherungsdokumente
                       als PDF samt Wahrheitsdatei <name>.wahrheit.json (Schema: BENCHMARK_SCHEMA.md)
    bewertung.py       lässt die Programm-Pipeline wie die Oberfläche laufen und prüft die AUSGABE
                       über alle Kanäle (Textebene, Formularfelder, Anmerkungen, Metadaten, Rohdaten,
                       Dateiname, OCR und Pixelvergleich bei Scans)
    normalisierung.py  gemeinsame Textnormalisierung für Generator und Bewertung
    kennungen.py       synthetische, aber prüfziffern-gültige Kennungen (IBAN, Steuer-ID, SV-Nr. …)
    stammdaten.py      Namen, Anschriften, Versicherer, Diagnosen … (alles frei erfunden)
    satz.py            kleine Satz-Engine (Zeilen, Absätze mit Silbentrennung, Tabellen) mit
                       Mitschrift der Wahrheitseinträge
    scan.py            macht aus Vektorseiten „Scans“ (dpi, JPEG, Schräglage, Rauschen, Fax, /Rotate)

Aufruf über das Kommandozeilenwerkzeug werkzeuge/benchmark.py.
"""

SCHEMA_VERSION = 1

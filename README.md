PDF-Anonymisierer

Dokumente sicher für KI-Dienste machen — personenbezogene Daten automatisch erkennen und echt entfernen.

Ein lokales Windows-Tool, das PDFs (auch eingescannte!) nach personenbezogenen Daten durchsucht und diese durch lesbare Platzhalter ersetzt. Damit lassen sich Versicherungsdokumente, Verträge und Schreiben gefahrlos an ChatGPT, Claude & Co. weitergeben — ohne Kundendaten preiszugeben.


🇩🇪 Entwickelt für deutsche Dokumente (Versicherungen, Behörden, Verträge). Läuft zu 100 % lokal — kein Datum verlässt den Rechner.




Was wird automatisch erkannt?

KategorieBeispielErsetzt durchPersonennamen (KI-Erkennung, spaCy)Max Mustermann[PERSON A]IBANs (mit Prüfziffern-Kontrolle)DE89 3704 0044 …[IBAN]Steuer-IDs (amtliche Prüfziffer, auch freistehend)91064389278[STEUER-ID]Geburtsdaten (auch Formularlayouts)geb. am 02.09.1983[GEB-DATUM]Adressen (Straße + Nr., PLZ + Ort)Hauptstraße 12a[ADRESSE]Telefonnummern & E-Mail-Adressen0171 2345678[TELEFON]Vertrags-/Kunden-/Schein-/ZulagenummernLV-2024-887766[VERTRAGS-NR]Sozialversicherungs- & Kindergeldnummern009FK407160[KINDERGELD-NR]Kfz-Kennzeichen (optional)NM-XY 123[KENNZEICHEN]

Der Clou: Platzhalter sind konsistent — [PERSON A] bleibt im ganzen Dokument dieselbe Person. Eine KI kann das Dokument also weiterhin sinnvoll auswerten ("Person A ist der Versicherungsnehmer, Person B die Ehefrau"), nur eben ohne echte Daten.

Warum nicht einfach schwarze Balken?

Weil die meisten "Schwärzungen" keine sind: Ein Balken über dem Text lässt sich per Copy & Paste umgehen. Dieses Tool entfernt den Text wirklich aus der Datei (PDF-Redaction), leert die Metadaten (Autor, Titel) und löscht bei Scans auch die Bildpixel unter der Fundstelle.

Funktionen


🖱️ Drag & Drop für einzelne PDFs oder ganze Ordner (inkl. Unterordner)
🔍 Prüfliste vor dem Schwärzen — jeder Fund einzeln an-/abwählbar
📷 OCR für eingescannte PDFs (Tesseract, deutsch) — inkl. Entfernung der Bildpixel
⚠️ Blinder-Fleck-Warnung: kaum lesbare Scan-Seiten werden ausdrücklich gemeldet statt still übersprungen
✅ Automatische Selbstkontrolle: nach dem Schwärzen wird jedes Dokument gegengelesen (bei Scans per erneutem OCR)
📝 Whitelist/Blacklist: eigene Begriffe immer bzw. nie schwärzen
🗂️ Originale bleiben unverändert; Ergebnisse landen im Unterordner anonymisiert


Installation (Windows)


Repository als ZIP herunterladen und entpacken, z. B. nach C:\PDF-Anonymisierer
Doppelklick auf Installieren.bat — richtet automatisch ein:

Python (falls nicht vorhanden, via winget)
Pakete: PyMuPDF, tkinterdnd2, spaCy + deutsches Sprachmodell
Tesseract-OCR mit deutscher Sprachdatei
Desktop-Verknüpfung "PDF-Anonymisierer"





Danach genügt der Doppelklick auf die Desktop-Verknüpfung.

Weitergabe an Kollegen: EXE-bauen.bat erzeugt via PyInstaller eine eigenständige PDF-Anonymisierer.exe — beim Empfänger ist keine Installation nötig (für Scan-Unterstützung dort zusätzlich: winget install UB-Mannheim.TesseractOCR).

Benutzung


PDFs oder Ordner in die blaue Fläche ziehen
Analysieren klicken → Fundliste erscheint
Liste prüfen (Doppelklick = Fund an/aus), dann Schwärzen starten


⚠️ Wichtiger Hinweis (bitte lesen!)

Keine automatische Erkennung ist zu 100 % zuverlässig. Ungewöhnliche Namen, schlechte Scanqualität, Handschrift und Unterschriften können durchrutschen — Handschriftliches erkennt die OCR grundsätzlich nicht. Dieses Tool ist ein starkes Sicherheitsnetz, ersetzt aber nicht die menschliche Kontrolle:


Die Fundliste vor dem Schwärzen ansehen
Das Ergebnis stichprobenartig öffnen, bevor es an einen KI-Dienst geht
Warnungen im Protokoll ernst nehmen (insbesondere die Blinder-Fleck-Warnung bei Scans)


Die Verantwortung für die DSGVO-konforme Weitergabe bleibt beim Nutzer.

Technik


Python 3.10+ · PyMuPDF (echte PDF-Redaction) · spaCy de_core_news_md (Namenserkennung) · Tesseract (OCR) · tkinter (GUI)
Muster-Erkennung mit Validierung statt blindem Regex: IBAN-Prüfsumme (Mod 97), Steuer-IdNr-Prüfziffer (§ 139b AO) — so werden freistehende IDs erkannt, ohne dass Zufallszahlen anschlagen
Bruchstück-Filter verhindert, dass z. B. Telefonnummern-Muster mitten in IBANs zugreifen


Lizenz

MIT — Nutzung auf eigene Verantwortung, ohne Gewähr (siehe Hinweis oben).

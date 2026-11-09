# Hinweise zu Drittkomponenten

Der eigene Code des PDF-Anonymisierers steht unter der MIT-Lizenz (siehe `LICENSE`).
Das Programm nutzt – und eine mit `EXE-bauen.bat` erzeugte EXE **bündelt** – die folgenden
Komponenten mit eigenen Lizenzen. Wer die EXE oder dieses Repository an Dritte weitergibt,
gibt diese Datei mit.

| Komponente | Version (Stand 0.2.0) | Lizenz | Quelle |
|---|---|---|---|
| PyMuPDF (Python-Bindung) und MuPDF (Artifex Software) | PyMuPDF 1.24–2.x, MuPDF 1.26–1.28 | **AGPL-3.0** oder kommerzielle Artifex-Lizenz | https://github.com/pymupdf/PyMuPDF · https://mupdf.com |
| Tesseract-OCR-Sprachdatei `deu.traineddata` (tessdata_fast) | tessdata_fast 4.1.0 | Apache-2.0 | https://github.com/tesseract-ocr/tessdata_fast |
| Tesseract-OCR-Engine (statisch in PyMuPDF enthalten) | 5.x | Apache-2.0 | https://github.com/tesseract-ocr/tesseract |
| spaCy (Explosion) | 3.8.x | MIT | https://github.com/explosion/spaCy |
| spaCy-Modell `de_core_news_md` (Explosion) | 3.8.0 | MIT (Modell); Trainingsdaten siehe unten | https://github.com/explosion/spacy-models |
| tkinterdnd2 (Python-Wrapper) | 0.4+ | MIT | https://github.com/Eliav2/tkinterdnd2 |
| TkDND (Tk-Erweiterung, in tkinterdnd2 enthalten) | 2.9.x | MIT-ähnlich (siehe Paket) | https://github.com/petasis/tkdnd |
| Python, tkinter, Tcl/Tk | 3.10–3.15 | PSF-Lizenz; Tcl/Tk BSD-ähnlich | https://www.python.org · https://www.tcl.tk |
| PyInstaller (nur Werkzeug für den EXE-Bau; Bootloader steckt in der EXE) | 6.x | GPL-2.0-or-later **mit Ausnahme**, die die Weitergabe gebauter Programme unter beliebiger Lizenz erlaubt | https://github.com/pyinstaller/pyinstaller |
| transitive Abhängigkeiten von spaCy (numpy, thinc, blis, srsly, cymem, preshed, murmurhash, catalogue, wasabi, pydantic, typer, …) | – | BSD-3 / MIT | PyPI |

## PyMuPDF / MuPDF (AGPL-3.0)

PyMuPDF ist „Dual Licensed – GNU AFFERO GPL 3.0 or Artifex Commercial License“. Folgen:

- **Nutzung im eigenen Büro** (auch durch Kollegen desselben Unternehmens): keine
  Pflichten, interne Weitergabe ist keine „Verbreitung“ im Sinne der AGPL.
- **Weitergabe der EXE an Dritte** (andere Maklerbetriebe, Pool-Partner, Veröffentlichung):
  Die EXE enthält PyMuPDF/MuPDF und wird insgesamt unter AGPL-3.0-Bedingungen
  weitergegeben. Empfänger müssen den Lizenztext erhalten
  (https://www.gnu.org/licenses/agpl-3.0.html) und Zugang zum vollständigen Quelltext
  bekommen – für den eigenen Code reicht der Link auf dieses Repository, für PyMuPDF/MuPDF
  der Link auf die oben genannten Quellen bzw. die auf PyPI veröffentlichten Quellpakete.
- **Kommerzielle Weitergabe** oder Einbau in ein proprietäres Produkt: Artifex-Lizenz
  prüfen (https://artifex.com/licensing/).

## Tesseract-Sprachdatei `tessdata/deu.traineddata`

Aus dem Repository `tessdata_fast` (Copyright 1988–1995 Hewlett Packard Company,
2006–2022 Google Inc.), lizenziert unter der Apache License, Version 2.0:
http://www.apache.org/licenses/LICENSE-2.0. Die Datei wird unverändert mitgeliefert.
Die Tesseract-Engine selbst ist in PyMuPDF statisch enthalten (ebenfalls Apache-2.0).

## spaCy-Modell `de_core_news_md` 3.8.0

Laut `meta.json` des Modells: Lizenz **MIT**, Autor Explosion. Trainingsquellen laut
`meta.json`: TIGER Corpus (kommerziell lizenziert durch Explosion), Tiger2Dep (Zitat, kein
Code im Modell), WikiNER (CC BY 4.0), Explosion fastText-Vektoren (CC0). Das Modell wird als
Wheel von GitHub installiert (`requirements.txt`).

## tkinterdnd2 / TkDND

tkinterdnd2 steht unter MIT (Klassifizierer des Pakets: „License :: OSI Approved :: MIT
License“). Es enthält die kompilierte Tk-Erweiterung TkDND von George Petasis; deren
Lizenztext liegt dem Paket bei (`tkinterdnd2/tkdnd/<plattform>/`). In der EXE wird nur der
für Windows x64 nötige Ordner gebündelt.

## MIT-Lizenztext (für spaCy, de_core_news_md, tkinterdnd2)

> Permission is hereby granted, free of charge, to any person obtaining a copy of this
> software and associated documentation files (the "Software"), to deal in the Software
> without restriction, including without limitation the rights to use, copy, modify,
> merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
> permit persons to whom the Software is furnished to do so, subject to the following
> conditions: The above copyright notice and this permission notice shall be included in
> all copies or substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS IS",
> WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
> WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
> IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
> OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT
> OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

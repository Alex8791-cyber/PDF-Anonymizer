# Hinweise zu Drittkomponenten

Der eigene Code des PDF-Anonymisierers steht unter der MIT-Lizenz (siehe `LICENSE`).
Das Programm nutzt – und eine mit `EXE-bauen.bat` erzeugte EXE **bündelt** – die folgenden
Komponenten mit eigenen Lizenzen. Wer die EXE oder dieses Repository an Dritte weitergibt,
gibt diese Datei mit. `EXE-bauen.bat` legt sie zusammen mit `LICENSE.txt`, `README.md` und dem
vollständigen AGPL-Text `licenses/AGPL-3.0.txt` in den Programmordner der EXE – damit sind sie
auch in der ZIP, die weitergegeben wird.

| Komponente | Version (Stand 11/2026) | Lizenz | Quelle |
|---|---|---|---|
| PyMuPDF (Python-Bindung) und MuPDF (Artifex Software) | PyMuPDF ab 1.24.10 (MuPDF 1.24.9) bis 2.x; pip installiert derzeit 2.1 (MuPDF 1.28.6) bzw. mit Python 3.10, 3.15 und auf ARM64 1.28.2 (MuPDF 1.28.2) | **AGPL-3.0** oder kommerzielle Artifex-Lizenz | https://github.com/pymupdf/PyMuPDF · https://mupdf.com |
| Tesseract-OCR-Sprachdatei `deu.traineddata` (tessdata_fast) | tessdata_fast 4.1.0 | Apache-2.0 | https://github.com/tesseract-ocr/tessdata_fast |
| Tesseract-OCR-Engine (statisch in PyMuPDF enthalten) | 5.x | Apache-2.0 | https://github.com/tesseract-ocr/tesseract |
| spaCy (Explosion) | 3.8.x | MIT | https://github.com/explosion/spaCy |
| spaCy-Modell `de_core_news_md` (Explosion) | 3.8.0 | MIT (Modell); Trainingsdaten siehe unten | https://github.com/explosion/spacy-models |
| tkinterdnd2 (Python-Wrapper) | 0.4+ (derzeit 0.7.0) | MIT | https://github.com/Eliav2/tkinterdnd2 |
| TkDND (Tk-Erweiterung, in tkinterdnd2 enthalten) | 2.10.3 (in tkinterdnd2 0.7.0) | BSD-artige Lizenz im Stil von Tcl/Tk (Text im Kopf von `tkdnd.tcl`) | https://github.com/petasis/tkdnd |
| Python, tkinter, Tcl/Tk | 3.10–3.15 | PSF-Lizenz; Tcl/Tk BSD-ähnlich | https://www.python.org · https://www.tcl.tk |
| PyInstaller (nur Werkzeug für den EXE-Bau; Bootloader steckt in der EXE) | 6.x | GPL-2.0-or-later **mit Ausnahme**, die die Weitergabe gebauter Programme unter beliebiger Lizenz erlaubt | https://github.com/pyinstaller/pyinstaller |
| transitive Abhängigkeiten von spaCy (numpy, thinc, blis, srsly, cymem, preshed, murmurhash, catalogue, wasabi, pydantic, typer, …); mit PyMuPDF 2.x zusätzlich psutil (BSD-3) und PyYAML (MIT), die numpy optional lädt und PyInstaller deshalb mitnimmt | – | BSD-3 / MIT | PyPI |
| weitere Abhängigkeiten von PyMuPDF 2.x – **nur pip-Installation, nicht in der EXE** (nichts im Programm lädt sie): onnxruntime (MIT), flatbuffers (Apache-2.0), protobuf (BSD-3), networkx (BSD-3), tabulate (MIT); dazu die leeren Übergangspakete pymupdf-layout und pymupdf4llm (Artifex) | – | MIT / BSD-3 / Apache-2.0 | PyPI |

## PyMuPDF / MuPDF (AGPL-3.0)

PyMuPDF ist „Dual Licensed – GNU AFFERO GPL 3.0 or Artifex Commercial License“. Das
PyMuPDF-Wheel enthält als Lizenzdatei nur diesen Einzeiler (`COPYING`), nicht den Lizenztext.
Der vollständige Text der GNU AGPL 3.0 liegt deshalb als **`licenses/AGPL-3.0.txt`** bei:
unverändert die Datei `COPYING` aus dem PyMuPDF-Quellpaket `pymupdf-2.1.tar.gz` (PyPI),
byte-gleich mit `COPYING` in den Repositories von PyMuPDF und MuPDF. `EXE-bauen.bat` kopiert
ihn in den Programmordner der EXE. Folgen:

- **Nutzung im eigenen Büro** (auch durch Kollegen desselben Unternehmens): keine
  Pflichten, interne Weitergabe ist keine „Verbreitung“ im Sinne der AGPL.
- **Weitergabe der EXE an Dritte** (andere Maklerbetriebe, Pool-Partner, Veröffentlichung):
  Die EXE enthält PyMuPDF/MuPDF und wird insgesamt unter AGPL-3.0-Bedingungen
  weitergegeben. Empfänger müssen den Lizenztext erhalten (liegt als `licenses/AGPL-3.0.txt`
  im Programmordner; online: https://www.gnu.org/licenses/agpl-3.0.html) und Zugang zum
  vollständigen Quelltext bekommen – für den eigenen Code reicht der Link auf dieses
  Repository, für PyMuPDF/MuPDF der Link auf die oben genannten Quellen bzw. die auf PyPI
  veröffentlichten Quellpakete.
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
Wheel von GitHub installiert (`requirements.txt`); seine Dateien `LICENSE` und
`LICENSES_SOURCES` liegen im Modellordner und damit auch in der EXE
(`_internal\de_core_news_md\de_core_news_md-3.8.0\`).

## tkinterdnd2 / TkDND

tkinterdnd2 steht unter MIT (Klassifizierer des Pakets: „License :: OSI Approved :: MIT
License“). Es enthält die kompilierte Tk-Erweiterung TkDND 2.10.3 von George Petasis
(National Centre for Scientific Research „Demokritos“, Athen) unter einer BSD-artigen Lizenz
im Stil von Tcl/Tk; ihr Text steht im Kopf der mitgelieferten Datei
`tkinterdnd2/tkdnd/<plattform>/tkdnd.tcl`. In der EXE wird nur der für Windows x64 nötige
Ordner gebündelt (samt `tkdnd.tcl`).

## MIT-Lizenztext (für spaCy, de_core_news_md, tkinterdnd2)

Copyright-Vermerke der unter MIT stehenden, gebündelten Komponenten:

- spaCy: Copyright (C) 2016-2024 ExplosionAI GmbH, 2016 spaCy GmbH, 2015 Matthew Honnibal
- de_core_news_md: Copyright 2021 ExplosionAI GmbH
- tkinterdnd2: Copyright (c) 2020 Philippe Gagné

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

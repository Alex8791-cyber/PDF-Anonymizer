"""Hilfen für lastunabhängige Laufzeittests (Runde 3).

Wanduhr-Schranken („dauerte < 2 s“) scheitern, sobald parallele Benchmarks oder ein langsamer CI-Runner die Kerne
belegen – der eigene Prozess wartet dann, er rechnet nicht mehr. Die Laufzeittests prüfen deshalb, was eine echte
Verschlechterung ausmacht, mit Größen, die von der Last kaum abhängen:

  cpu_sekunden(funktion, wiederholungen)  CPU-Zeit dieses Prozesses statt Wanduhr (das Minimum mehrerer Läufe
                                          glättet geteilte Kerne und Caches); die Speicherbereinigung ist dabei
                                          aus, wie bei timeit
  cpu_sekunden_abwechselnd({name: f})     dasselbe für mehrere Größen im Wechsel (klein, groß, klein, groß):
                                          beide sehen dieselbe Last, das Verhältnis bleibt stabil
  wachstum(klein, gross, faktor)          wie viel schneller die Zeit wächst als die Eingabe: 1,0 = linear.
                                          Gemessen wird mit großer Spreizung (n gegen 8n bzw. 16n): ein Anteil
                                          Funde x Seiten oder Funde² wächst quadratisch, die lineare Grundlast nur
                                          mit dem Faktor – erst bei großer Spreizung überwiegt er. Bei n gegen 4n
                                          ging eine echte Funde-x-Seiten-Regression in der Grundlast unter
                                          (Schwärzung: Verhältnis 7,5 bei Schranke 8; Befund Runde 3a)
  gemessener_ocr_arbeiter(...)            Ersatz für ocr._ocr_worker, der in jedem Arbeitsprozess Prozessnummer,
                                          Beginn und Ende jedes Auftrags aufschreibt (Verzeichnis in der
                                          Umgebungsvariablen UMGEBUNG) – so lässt sich zeigen, dass zwei Arbeiter
                                          gleichzeitig rechneten und jede Seite genau einmal gelesen wurde
  auftraege(ordner)                       die aufgeschriebenen Aufträge als Lauf(prozess, seite, beginn, ende)
  groesste_ueberlappung(laeufe)           größter Anteil, zu dem sich zwei Aufträge verschiedener Prozesse
                                          zeitlich überdecken (1.0 = der kürzere lief ganz neben dem anderen)

Dieses Modul ist kein Testmodul (wird nicht gesammelt); die Arbeitsprozesse des OCR-Pools (Start-Methode "spawn")
importieren es über den von pytest gesetzten Suchpfad.
"""

import gc
import os
import time
from collections import namedtuple
from pathlib import Path

from anonymisierer import ocr as _ocr

UMGEBUNG = "PDF_ANONYMISIERER_TEST_ARBEITSZEITEN"
_ORIGINAL_OCR_ARBEITER = _ocr._ocr_worker          # beim Import festgehalten: Tests ersetzen ihn im Modul

Lauf = namedtuple("Lauf", "prozess seite beginn ende")


def cpu_sekunden(funktion, wiederholungen: int = 1):
    """(Ergebnis des letzten Aufrufs, kleinste CPU-Zeit dieses Prozesses in Sekunden über die Wiederholungen).
    Zählt alle Threads des Prozesses (time.process_time), nicht aber Wartezeit auf einen belegten Kern. Die
    Speicherbereinigung ist während des Aufrufs aus (wie bei timeit): ihre Läufe kosten mit der Zahl lebender
    Objekte mehr und ließen eine lineare Laufzeit überlinear aussehen (analysiere_text, 500 gegen 4000 Zeilen:
    Verhältnis gemessen 9,4 bis 10,5 mit, 8,5 bis 8,8 ohne Speicherbereinigung)."""
    beste, ergebnis = None, None
    for _ in range(max(1, wiederholungen)):
        ergebnis = None
        gc.collect()
        war_an = gc.isenabled()
        gc.disable()
        try:
            anfang = time.process_time()
            ergebnis = funktion()
            dauer = time.process_time() - anfang
        finally:
            if war_an:
                gc.enable()
        beste = dauer if beste is None else min(beste, dauer)
    return ergebnis, beste


def wachstum(zeit_klein: float, zeit_gross: float, faktor: float) -> float:
    """(zeit_gross / zeit_klein) / faktor, wenn die Eingabe um faktor wächst: 1,0 = linear, ein quadratischer
    Anteil hebt den Wert umso stärker, je größer faktor ist."""
    return zeit_gross / max(zeit_klein, 1e-6) / faktor


def cpu_sekunden_abwechselnd(funktionen: dict, wiederholungen: int = 2) -> dict:
    """{Name: (Ergebnis des letzten Aufrufs, kleinste CPU-Zeit)} für mehrere Messungen, die sich ABWECHSELN
    (klein, groß, klein, groß …): beide Größen sehen dieselbe Last, ein Lastwechsel mitten in der Messung verzerrt
    ihr Verhältnis nicht (geteilte Kerne bremsen auch die CPU-Zeit etwas)."""
    beste: dict = {}
    for _ in range(max(1, wiederholungen)):
        for name, funktion in funktionen.items():
            ergebnis, dauer = cpu_sekunden(funktion)
            beste[name] = (ergebnis, min(dauer, beste[name][1]) if name in beste else dauer)
    return beste


def gemessener_ocr_arbeiter(*args, **kwargs):
    """Liest wie ocr._ocr_worker und schreibt danach „Prozess Seite Beginn Ende“ (Wanduhr des Systems, über
    Prozesse vergleichbar) in eine Datei je Prozess im Verzeichnis aus UMGEBUNG."""
    beginn = time.time()
    try:
        return _ORIGINAL_OCR_ARBEITER(*args, **kwargs)
    finally:
        ende = time.time()
        ordner = os.environ.get(UMGEBUNG)
        if ordner:
            seite = args[1] if len(args) > 1 else kwargs.get("seite_nr0", -1)
            with open(Path(ordner) / f"{os.getpid()}.txt", "a", encoding="utf-8") as datei:
                datei.write(f"{os.getpid()} {int(seite)} {beginn!r} {ende!r}\n")


def auftraege(ordner) -> list:
    """Alle aufgeschriebenen Aufträge, nach Beginn sortiert."""
    laeufe = []
    for datei in Path(ordner).glob("*.txt"):
        for zeile in datei.read_text(encoding="utf-8").splitlines():
            prozess, seite, beginn, ende = zeile.split()
            laeufe.append(Lauf(int(prozess), int(seite), float(beginn), float(ende)))
    return sorted(laeufe, key=lambda lauf: lauf.beginn)


def groesste_ueberlappung(laeufe) -> float:
    """Größter Anteil (0..1), zu dem ein Auftrag zeitgleich mit einem Auftrag eines ANDEREN Prozesses lief,
    bezogen auf den kürzeren der beiden. 0.0, wenn alle Aufträge nacheinander oder in einem Prozess liefen."""
    beste = 0.0
    for i, a in enumerate(laeufe):
        for b in laeufe[i + 1:]:
            if a.prozess == b.prozess:
                continue
            gemeinsam = min(a.ende, b.ende) - max(a.beginn, b.beginn)
            kuerzer = min(a.ende - a.beginn, b.ende - b.beginn)
            if gemeinsam > 0 and kuerzer > 0:
                beste = max(beste, min(1.0, gemeinsam / kuerzer))
    return beste

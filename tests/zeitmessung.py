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
                                          Gemessen wird mit großer Spreizung (n gegen 8n bzw. 16n) und mit einer
                                          Schranke knapp über linear: ein quadratischer Anteil (Funde x Seiten,
                                          Funde²) zählt in der kleinen Messung fast nicht, in der großen voll – je
                                          größer die Spreizung, desto deutlicher. Bei n gegen 4n mit Schranke 8
                                          (fast das Doppelte von linear) ging eine echte Funde-x-Seiten-Regression
                                          unter (Schwärzung: Verhältnis 6,0 bis 9,4; Befund Runde 3a)
  wachstum_messen(klein, gross, faktor)   beides in einem Schritt, auch für kurze Aufrufe: faktor-mal klein gegen
                                          einmal gross (bei linearer Laufzeit dieselbe Arbeit), so oft hintereinander,
                                          dass jede Messung mindestens 0,1 s CPU-Zeit dauert (Runde 3b)
  gemessener_ocr_arbeiter(...)            Ersatz für ocr._ocr_worker, der in jedem Arbeitsprozess Prozessnummer,
                                          Beginn und Ende jedes Auftrags aufschreibt (Verzeichnis in der
                                          Umgebungsvariablen UMGEBUNG) – so lässt sich zeigen, dass zwei Arbeiter
                                          gleichzeitig rechneten und jede Seite genau einmal gelesen wurde
  auftraege(ordner)                       die aufgeschriebenen Aufträge als Lauf(prozess, seite, beginn, ende)
  groesste_ueberlappung(laeufe)           größter Anteil, zu dem sich zwei Aufträge verschiedener Prozesse
                                          zeitlich überdecken (1.0 = der kürzere lief ganz neben dem anderen)

Auflösung unter Windows (Runde 3b): time.process_time() liest dort GetProcessTimes, das die CPU-Zeit nur in Schritten
des Zeitgebers zählt (15,6 ms) – ein Aufruf von 10 ms misst 0 oder 15,6 ms. Absolute Schranken liegen deshalb
mehrere Schritte über null (ab 50 ms), Verhältnisse entstehen aus Messungen von mindestens 0,1 s (wachstum_messen:
höchstens ein Schritt Fehler je Messung, unter 16 %).

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


def wachstum_messen(klein, gross, faktor: int, wiederholungen: int = 2, mindestens: float = 0.1) -> tuple:
    """(wachstum, CPU-Zeit je Aufruf von klein, CPU-Zeit je Aufruf von gross) für zwei Aufrufe ohne Argumente, deren
    Eingaben sich um `faktor` unterscheiden (klein verarbeitet 1/faktor dessen, was gross verarbeitet). Gemessen
    werden `faktor` Aufrufe von klein gegen EINEN von gross: bei linearer Laufzeit dieselbe Arbeit, also gleich lange
    Messungen, und ihr Verhältnis ist das Wachstum (1,0 = linear; ein quadratischer Anteil hebt es bis auf `faktor`,
    feste Kosten je Aufruf senken es unter 1). Kurze Aufrufe laufen r-mal hintereinander, r so gewählt, dass gross
    allein mindestens `mindestens` Sekunden CPU-Zeit braucht – so bleibt der Fehler der Windows-Zählung (Schritte von
    15,6 ms) unter 16 % je Messung. Beide Messungen wechseln sich ab (cpu_sekunden_abwechselnd), es zählt je das
    Minimum; die Aufrufe davor (einmal klein, r-mal gross) wärmen Zwischenspeicher und Module auf."""
    klein()
    r, anfang = 0, time.process_time()
    while True:
        gross()
        r += 1
        if time.process_time() - anfang >= mindestens:
            break
    gemessen = cpu_sekunden_abwechselnd({"klein": lambda: [klein() for _ in range(r * faktor)],
                                         "gross": lambda: [gross() for _ in range(r)]}, wiederholungen)
    zeit_klein, zeit_gross = gemessen["klein"][1], gemessen["gross"][1]
    return wachstum(zeit_klein / faktor, zeit_gross, faktor), zeit_klein / (r * faktor), zeit_gross / r


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

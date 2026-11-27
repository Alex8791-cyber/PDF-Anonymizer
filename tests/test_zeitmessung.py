"""Tests für tests/zeitmessung.py – die Messung, auf die sich die lastunabhängigen Laufzeittests verlassen.

Befund der Gegenprüfung (Runde 3b): mit der Windows-Zählung der CPU-Zeit (GetProcessTimes zählt in Schritten von
15,625 ms) las wachstum_messen ein wahres Wachstum von 1,2 als bis zu 1,6 – über der Schranke 1,5 der Muster-Tests –,
weil jede Messung nur 0,1 s dauerte (gut sechs Schritte) und der Zählfehler BEIDER Messungen ins Verhältnis eingeht.
Die Tests hier bilden die Windows-Uhr mit einem künstlichen CPU-Zähler nach, den die gemessenen Aufrufe selbst
weiterstellen: kein echtes Rechnen, keine Last, auf jedem Rechner dieselben Zahlen.
"""

import time

import pytest

import zeitmessung

SCHRITT = 0.015625                                   # Takt der Windows-Zählung


class KuenstlicheUhr:
    """CPU-Zähler in Sekunden; als time.process_time() liefert er ganze Schritte (schritt=0: genau). Jedes Ablesen
    kostet 2 µs, sonst käme die Suche nach dem Schritt (uhr_schritt) nie weiter."""

    def __init__(self, schritt: float, phase: float = 0.0):
        self.schritt = schritt
        self.zaehler = 100.0 + phase * schritt

    def ablesen(self) -> float:
        self.zaehler += 2e-6
        return (self.zaehler // self.schritt) * self.schritt if self.schritt else self.zaehler

    def aufrufe(self, sekunden_klein: float, sekunden_gross: float) -> tuple:
        """(klein, gross): Aufrufe ohne Argumente, die je so viel CPU-Zeit verbrauchen."""
        def klein():
            self.zaehler += sekunden_klein

        def gross():
            self.zaehler += sekunden_gross
        return klein, gross


@pytest.fixture
def uhr(monkeypatch):
    """stellen(schritt, phase) setzt eine neue künstliche Uhr als time.process_time ein (danach wieder die echte)."""
    monkeypatch.setattr(zeitmessung.gc, "collect", lambda: 0)     # zählt auf der künstlichen Uhr nicht, kostet nur

    def stellen(schritt: float = SCHRITT, phase: float = 0.0) -> KuenstlicheUhr:
        neu = KuenstlicheUhr(schritt, phase)
        monkeypatch.setattr(time, "process_time", neu.ablesen)
        return neu
    return stellen


def test_uhr_schritt_ist_der_takt_der_zaehlung(uhr):
    """Maßgeblich ist der Takt, in dem die Zahl weiterzählt; time.get_clock_info() meldet unter Windows 100 ns."""
    echt = zeitmessung.uhr_schritt()
    print(f"Prozessuhr dieses Rechners: Schritt {echt * 1000:.4f} ms")
    assert 0 < echt < 0.1
    uhr(SCHRITT, phase=0.3)
    assert zeitmessung.uhr_schritt() == SCHRITT
    uhr(schritt=0)
    assert zeitmessung.uhr_schritt() == pytest.approx(2e-6)


@pytest.mark.parametrize("wahr", [1.0, 1.2, 1.3])
def test_wachstum_unter_windows_zaehlung_nah_am_wahren_wert(uhr, wahr):
    """Der Befund nachgestellt: gross braucht 0,5 bis 114 ms je Aufruf (die Muster-Tests 1,2 bis 114 ms), klein
    1/(8 x wahr) davon, die Uhr beginnt in verschiedenen Phasen ihres Takts. Jede Messung dauert mindestens 20
    Schritte (gross mehr als 19, klein mehr als 19/wahr): das gemessene Wachstum liegt höchstens um den Faktor
    (1 + 1/19) / (1 - wahr/19) neben dem wahren – 1,11 bei linearer Laufzeit, 1,13 bei 1,3 –, ein wahres Wachstum bis
    1,3 bleibt also unter 1,5. Mit 0,1 s je Messung (bis zum Befund) las sich hier das wahre 1,2 als 1,6 (gross
    1,625 ms, Phase 0) und das wahre 1,3 als 1,75."""
    grenze = (1 + 1 / 19) / (1 - wahr / 19)
    gemessen, je_aufruf = [], []
    for gross_ms in (0.5, 1.625, 7.3, 45.0, 114.0):
        for phase in (0.0, 0.25, 0.5, 0.75):
            klein, gross = uhr(SCHRITT, phase).aufrufe(gross_ms / 1000 / (8 * wahr), gross_ms / 1000)
            wachstum, _, zeit_gross = zeitmessung.wachstum_messen(klein, gross, 8)
            gemessen.append((round(wachstum / wahr, 3), gross_ms, phase))
            je_aufruf.append((round(zeit_gross * 1000 / gross_ms, 3), gross_ms, phase))
    zu_gross, zu_klein = max(gemessen), min(gemessen)
    print(f"wahres Wachstum {wahr}: gemessen das {zu_klein[0]:.3f}- bis {zu_gross[0]:.3f}-fache")
    assert zu_gross[0] < grenze and zu_klein[0] > 1 / grenze, (grenze, zu_klein, zu_gross)
    assert zu_gross[0] * wahr < 1.5
    assert 0.94 < min(je_aufruf)[0] and max(je_aufruf)[0] < 1.06, (min(je_aufruf), max(je_aufruf))   # Zeit je Aufruf


def test_quadratische_laufzeit_bleibt_sichtbar(uhr):
    """Wofür die Wachstumsprüfungen da sind: 8-fache Eingabe, 64-fache Zeit – mit grober Uhr und Nachmessung an der
    Schranke weiter weit über 1,5 (die kleine Messung dauert dann nur ein Achtel und zählt gröber)."""
    for phase in (0.0, 0.5):
        klein, gross = uhr(SCHRITT, phase).aufrufe(0.2e-3, 64 * 0.2e-3)
        wachstum = zeitmessung.wachstum_messen(klein, gross, 8, schranke=1.5)[0]
        assert 6 < wachstum < 11, (phase, wachstum)                     # um 8; klein zählt nur 2 bis 6 Schritte


def test_nachmessung_an_der_schranke(monkeypatch, capsys):
    """An oder über der Schranke wird einmal nachgemessen – doppelt so lang, ein Wechsel mehr – und der kleinere
    Wert zählt: ein Ausreißer (1,55) fällt weg, eine Regression (7,9 und 8,1) bleibt. Ohne Schranke und unter ihr
    bleibt es bei einer Messung."""
    aufrufe = []

    def messungen(*werte):
        folge = iter(werte)

        def messen(klein, gross, faktor, wiederholungen, dauer):
            aufrufe.append((wiederholungen, dauer))
            return next(folge), 0.001, 0.008
        monkeypatch.setattr(zeitmessung, "_wachstum_einmal", messen)
        aufrufe.clear()

    monkeypatch.setattr(zeitmessung, "uhr_schritt", lambda: SCHRITT)
    messungen(1.55, 1.02)
    assert zeitmessung.wachstum_messen(None, None, 8, schranke=1.5)[0] == 1.02
    assert aufrufe == [(2, 20 * SCHRITT), (3, 40 * SCHRITT)]
    assert "wachstum 1.55 an oder über der Schranke 1.5, nachgemessen" in capsys.readouterr().out
    messungen(7.9, 8.1)
    assert zeitmessung.wachstum_messen(None, None, 8, schranke=1.5)[0] == 7.9
    messungen(1.49)
    assert zeitmessung.wachstum_messen(None, None, 8, schranke=1.5)[0] == 1.49
    assert aufrufe == [(2, 20 * SCHRITT)]
    messungen(1.55)
    assert zeitmessung.wachstum_messen(None, None, 8, mindestens=0.5)[0] == 1.55
    assert aufrufe == [(2, 0.5)]

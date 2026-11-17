"""Weg der Schwärzung im Entwicklungs-Benchmark (werkzeuge/benchmark.py --weg) und der Schwärz-Auftrag, den
Oberfläche und Benchmark teilen (anonymisierer/auftrag.py).

Befund (Runde 3b): Der Benchmark gab jeden Fund der Analyse unverändert an die Schwärzung („alle Funde angehakt“). Die
Oberfläche schickt ohne Eingriff der Nutzerin einen anderen Auftrag: ganz abgewählte Funde (in „Hoch“ die nur
angebotenen Gesundheitsdaten) bleiben weg, abgewählte Bildfunde gehen mit allen Bereichen abgewählt mit, dazu kommen
Seitenmodell und Nebenkanäle der Analyse und „Freigabe vor Weitergabe“. Geprüft wird:
* der Auftrag aus den Häkchen und die Parameter der Schwärzung (rein, ohne Engine);
* Weg engine ruft das Programm genau wie bisher auf (dieselben Argumente, dieselbe Form des Ergebnisses);
* Weg oberflaeche schickt einen nur angebotenen Fund nicht mit – eine Schwärzung, die jeden übergebenen Fund schwärzt
  (wie Programmversionen ohne Einzelstellen), schwärzt ihn deshalb nur im Weg engine; mit der echten Engine bleibt er
  in beiden Wegen lesbar (sie schwärzt nur Stellen mit „an“), der Auftrag unterscheidet sich trotzdem;
* Oberfläche und Benchmark analysieren mit denselben Einstellungen und schicken für dasselbe Analyseergebnis denselben
  Auftrag mit denselben Parametern an die Schwärzung (unter Xvfb, echte Engine).
"""

import functools
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

import pymupdf as fitz

from conftest import braucht_modell, braucht_ocr
from anonymisierer import auftrag, muster
from test_gui import ARZTBERICHT, FakeOcr, pdf_schreiben, starte_lauf
from test_gui import _prozesszustand, app, dialoge, root, umgebung  # noqa: F401,F811 (Fixtures)
from werkzeuge.benchmark import bewertung, generator

WURZEL = Path(__file__).resolve().parents[1]
STANDARD_AN = {k[0] for k in muster.KATEGORIEN if k[4]}
KEIN_DISPLAY = not os.environ.get("DISPLAY") and sys.platform != "win32"


def _benchmark_cli():
    """werkzeuge/benchmark.py (Kommandozeile; der Name „werkzeuge.benchmark“ gehört dem Paket daneben)."""
    spec = importlib.util.spec_from_file_location("benchmark_cli", WURZEL / "werkzeuge" / "benchmark.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


# ----------------------------------------------------------------------
# Auftrag aus den Häkchen (rein)
# ----------------------------------------------------------------------
def _stelle(start=0, ende=4, an=True, **mehr) -> dict:
    return dict({"seite": 0, "start": start, "ende": ende, "an": an}, **mehr)


def _funde() -> list:
    return [
        {"id": "f1", "kategorie": "namen", "text": "Max Muster", "stellen": [_stelle(), _stelle(10, 20)]},
        {"id": "f2", "kategorie": "iban", "text": "DE89 3704", "stellen": [_stelle(), _stelle(30, 40, an=False)]},
        {"id": "f3", "kategorie": "diagnose", "text": "Lumboischialgie", "stellen": [_stelle(50, 65, an=False)]},
        {"id": "f4", "kategorie": "lichtbild", "text": "", "stellen": [{"seite": 0, "bereich": [1, 2, 30, 40]}]},
        {"id": "f5", "kategorie": "lichtbild", "text": "",
         "stellen": [{"seite": 0, "bereich": [5, 6, 50, 60], "an": False}]},
        {"id": "f6", "kategorie": "email", "text": "a@b.de"},                # ältere Engine: Fund ohne Stellen
    ]


def test_haekchen_nach_der_analyse_und_auftrag_mit_einzelstellen():
    """Mit Einzelstellen folgen die Häkchen den Stellen: nur angeboten (alle Stellen abgewählt) = „aus“. Der Auftrag
    enthält angehakte und teilweise angehakte Funde, dahinter abgewählte Bildfunde mit allen Bereichen abgewählt; der
    nur angebotene Fund (Diagnose) fehlt. Nur Kopien – das Analyseergebnis bleibt unverändert."""
    funde = _funde()
    vorher = json.dumps(funde, sort_keys=True)
    zustaende = [auftrag.standard_zustand(f, True) for f in funde]
    assert zustaende == ["an", "teil", "aus", "an", "aus", "an"]
    angehakt, bilder = auftrag.auftrag_funde(funde, zustaende, True)
    assert [f["id"] for f in angehakt] == ["f1", "f2", "f4", "f6"]
    assert [f["id"] for f in bilder] == ["f5"] and [st["an"] for st in bilder[0]["stellen"]] == [False]
    assert [st["an"] for st in angehakt[1]["stellen"]] == [True, False]       # teilweise: Stellen wie gewählt
    assert all(k is not f for k in angehakt + bilder for f in funde)
    assert angehakt[0]["stellen"] is not funde[0]["stellen"] and angehakt[0]["stellen"] == funde[0]["stellen"]
    assert json.dumps(funde, sort_keys=True) == vorher
    e = {"funde": funde, "ocr_cache": {0: []}, "modell": object(), "nebenkanaele": {"personenbezug": False}}
    a = auftrag.auftrag_bauen(e, zustaende, True)
    assert [f["id"] for f in a["funde"]] == ["f1", "f2", "f4", "f6", "f5"]
    assert a["modell"] is e["modell"] and a["ocr_cache"] is e["ocr_cache"] and a["nebenkanaele"] == {
        "personenbezug": False}
    assert a["bereiche"] == {} and a["stellen"] == {} and not a["ohne_haken"] and a["gefunden"]


def test_haekchen_ohne_einzelstellen_und_nur_angebotene_funde():
    """Ohne Einzelstellen (kein Seitenmodell oder die Engine nimmt keins an) gilt das Häkchen der Zeile – nach der
    Analyse „an“ für jeden Fund; kein Modell im Auftrag. Ein in der Zeile abgewähltes Lichtbild geht trotzdem mit
    allen Bereichen abgewählt mit. Stehen nur angebotene Funde in der Liste, ist der Auftrag „ohne Haken“."""
    funde = _funde()
    zustaende = [auftrag.standard_zustand(f, False) for f in funde]
    assert zustaende == ["an"] * 6
    e = {"funde": funde, "ocr_cache": {}, "modell": object(), "nebenkanaele": ["kein dict"]}
    a = auftrag.auftrag_bauen(e, zustaende, False)
    assert [f["id"] for f in a["funde"]] == ["f1", "f2", "f3", "f4", "f5", "f6"]
    assert a["modell"] is None and a["nebenkanaele"] is None
    assert a["funde"][2]["stellen"] is funde[2]["stellen"]     # ohne Einzelstellen: die Stellen der Analyse
    abgewaehlt = ["an", "an", "an", "an", "aus", "an"]
    a = auftrag.auftrag_bauen(e, abgewaehlt, False)
    assert a["funde"][-1]["id"] == "f5" and not any(st["an"] for st in a["funde"][-1]["stellen"])
    nur_angeboten = {"funde": [funde[2], funde[4]], "ocr_cache": {}}
    z = [auftrag.standard_zustand(f, True) for f in nur_angeboten["funde"]]
    a = auftrag.auftrag_bauen(nur_angeboten, z, True)
    assert z == ["aus", "aus"] and [f["id"] for f in a["funde"]] == ["f5"] and a["ohne_haken"] and a["gefunden"]
    with pytest.raises(ValueError):
        auftrag.auftrag_funde(funde, zustaende[:-1], True)        # je Fund ein Häkchen


def _neue_engine(pdf_pfad, funde, melde=None, fortschritt=None, abbruch=None, ocr=None, ocr_cache=None,
                 ziel_ordner=None, modell=None, manuelle_bereiche=None, manuelle_stellen=None,
                 freigabe_erforderlich=False, profil="hoch", nebenkanaele=None):
    raise AssertionError("nur die Signatur zählt")


def _alte_engine(pdf_pfad, funde, melde=None, fortschritt=None, abbruch=None, ocr=None, ocr_cache=None,
                 ziel_ordner=None):
    raise AssertionError("nur die Signatur zählt")


def test_parameter_der_schwaerzung_wie_in_der_oberflaeche():
    """Neue Parameter nur, wenn die Engine sie kennt; Seitenmodell nur mit Einzelstellen; „Freigabe vor Weitergabe“
    und bei Fotos immer die Freigabe; manuelle Markierungen nur, wenn es welche gibt."""
    e = {"funde": _funde(), "ocr_cache": {0: ["w"]}, "modell": object(), "nebenkanaele": {"personenbezug": True}}
    assert auftrag.einzelstellen_moeglich(e, _neue_engine) and not auftrag.einzelstellen_moeglich(e, _alte_engine)
    assert not auftrag.einzelstellen_moeglich(dict(e, modell=None), _neue_engine)
    neu, zustaende = auftrag.standard_auftrag(e, _neue_engine)
    assert zustaende == ["an", "teil", "aus", "an", "aus", "an"]
    p = auftrag.schwaerz_parameter(neu, auftrag.STANDARD_FREIGABE, auftrag.STANDARD_PROFIL, _neue_engine)
    assert p == {"ocr_cache": e["ocr_cache"], "nebenkanaele": e["nebenkanaele"], "modell": e["modell"],
                 "freigabe_erforderlich": True, "profil": "hoch"}
    assert auftrag.schwaerz_parameter(neu, False, "hoch", _neue_engine)["freigabe_erforderlich"] is False
    assert auftrag.schwaerz_parameter(dict(neu, foto=True), False, "hoch", _neue_engine)["freigabe_erforderlich"]
    markiert = dict(neu, bereiche={0: [fitz.Rect(1, 1, 9, 9)]}, stellen={0: [(3, 7, "[GESCHWÄRZT]")]})
    p = auftrag.schwaerz_parameter(markiert, True, "maximal", _neue_engine)
    assert p["manuelle_bereiche"] == markiert["bereiche"] and p["manuelle_stellen"] == markiert["stellen"]
    assert p["profil"] == "maximal"
    alt, _ = auftrag.standard_auftrag(e, _alte_engine)
    assert auftrag.schwaerz_parameter(alt, True, "hoch", _alte_engine) == {"ocr_cache": e["ocr_cache"]}


def test_status_wie_die_oberflaeche_ihn_zeigt():
    """_PRUEFEN nur wegen „Freigabe vor Weitergabe“ ist „Freigabe ausstehend“ ohne Grund – mit Verdacht, Resten,
    nicht lokalisierten Stellen oder einem Grund der Engine nicht."""
    def aus(**mehr):
        return dict({"fehler": None, "ausgabe": Path("anonym_01_PRUEFEN.pdf"), "status": "pruefen", "reste": [],
                     "verdacht": [], "stellen_nicht_lokalisiert": 0, "pruefen_gruende": ["Freigabe ausstehend"]},
                    **mehr)
    assert auftrag.ausgabe_status(aus(fehler="kaputt", ausgabe=None)) == "fehler"
    assert auftrag.ausgabe_status(aus(ausgabe=None)) == "keine"
    assert auftrag.ausgabe_status(aus()) == "pruefen" and auftrag.nur_freigabe_offen(aus(), "pruefen")
    fertig = aus(ausgabe=Path("anonym_01.pdf"), status="fertig", pruefen_gruende=[])
    assert auftrag.ausgabe_status(fertig) == "fertig" and auftrag.nur_freigabe_offen(fertig, "fertig")
    assert auftrag.ausgabe_status(dict(fertig, reste=["Max"])) == "pruefen"
    for mit_grund in (aus(verdacht=[{"text": "Max"}]), aus(reste=["Max"]), aus(stellen_nicht_lokalisiert=2),
                      aus(pruefen_gruende=["Seite 1: kein Text erkannt"])):
        assert not auftrag.nur_freigabe_offen(mit_grund, auftrag.ausgabe_status(mit_grund))


def test_standard_der_oberflaeche():
    """Schutzstufe „Hoch“ mit ihren Kategorien, „Freigabe vor Weitergabe“ an – die Einstellungen beim ersten Start."""
    assert auftrag.STANDARD_PROFIL == muster.STANDARD_PROFIL == "hoch"
    assert auftrag.standard_kategorien() == set(muster.PROFILE["hoch"]["aktive"])
    assert auftrag.STANDARD_FREIGABE is True
    assert auftrag.PROFILE is muster.PROFILE


# ----------------------------------------------------------------------
# Benchmark mit einer Attrappe der Engine (ohne Modell und OCR)
# ----------------------------------------------------------------------
ZEILEN = ["Arztbericht der Praxis am Markt", "Patient: Max Mustermann", "Diagnose: Lumboischialgie links (M54.4)",
          "Wir bitten um Rückruf."]
NAME, DIAGNOSE = "Max Mustermann", "Lumboischialgie links (M54.4)"


def _mini_korpus(ordner: Path) -> Path:
    """Ein Arztbericht mit Wahrheit: Name (Kern), Diagnose (erweitert), „Arztbericht“ (behalten)."""
    ordner.mkdir(parents=True)
    doc = fitz.open()
    seite = doc.new_page()
    for i, zeile in enumerate(ZEILEN):
        seite.insert_text((60, 80 + 20 * i), zeile, fontsize=11)
    pdf = ordner / "001_arztbrief.pdf"
    doc.save(pdf)
    woerter = seite.get_text("words")
    doc.close()

    def eintrag(nr, text, kategorie, erwartung, umfang):
        teile = text.split()
        start = next(i for i in range(len(woerter)) if [w[4] for w in woerter[i:i + len(teile)]] == teile)
        return {"id": f"e{nr}", "text": text, "kategorie": kategorie, "seite": 1, "erwartung": erwartung,
                "umfang": umfang, "kanal": "text", "bemerkung": "",
                "woerter": [[round(v, 1) for v in w[:4]] + [w[4]] for w in woerter[start:start + len(teile)]]}
    wahrheit = {"dokument": pdf.name, "typ": "arztbrief", "seiten": 1, "merkmale": [],
                "eintraege": [eintrag(1, NAME, "namen", "schwaerzen", "kern"),
                              eintrag(2, DIAGNOSE, "diagnose", "schwaerzen", "erweitert"),
                              eintrag(3, "Arztbericht", "kontext", "behalten", "kern")]}
    assert bewertung.pruefe_wahrheit(pdf, wahrheit) == []
    (ordner / "001_arztbrief.wahrheit.json").write_text(json.dumps(wahrheit, ensure_ascii=False), encoding="utf-8")
    return pdf


class _Lauf:
    """Attrappe des LaufWissens (ein Exemplar je Lauf)."""


class _JederFundEngine(bewertung.NullAnonymisierer):
    """Analyse mit zwei Funden – der Name angehakt, die Diagnose nur angeboten (Stelle abgewählt, wie in „Hoch“) – und
    eine Schwärzung, die JEDEN übergebenen Fund schwärzt, ohne die Stellen anzusehen (wie Programmversionen ohne
    Einzelstellen). Beide schneiden ihre Aufrufe mit; der Auftrag der Oberfläche kommt aus anonymisierer/auftrag.py."""

    auftrag = auftrag
    lauf_wissen = _Lauf

    def __init__(self):
        super().__init__()
        self.commit = "jeder-fund"
        self.kategorien = muster.KATEGORIEN
        self.analyse_aufrufe, self.schwaerz_aufrufe = [], []
        self.modell = object()
        self.nebenkanaele = {"metadaten": 0, "lesezeichen": 0, "anhaenge": 0, "xfa": False, "personenbezug": False}
        self._nr = 0

    def aktive(self) -> set:
        return set(STANDARD_AN)

    def analysiere_pdf(self, pdf, aktive, nie, immer, melde=None, ocr=None, profil="hoch", kundenliste=None,
                       lauf=None):
        self.analyse_aufrufe.append({"aktive": set(aktive), "nie": list(nie), "immer": list(immer), "ocr": ocr,
                                     "profil": profil, "lauf": lauf})
        text = "\n".join(ZEILEN)

        def fund(nr, kategorie, wert, an):
            s = text.index(wert)
            return {"id": f"f{nr}", "kategorie": kategorie, "anzeige": kategorie, "text": wert, "ersatz": "[X]",
                    "seiten": [1], "anzahl": 1, "kontext": "", "stellen": [_stelle(s, s + len(wert), an)]}
        return {"funde": [fund(1, "namen", NAME, True), fund(2, "diagnose", DIAGNOSE, False)], "warnungen": [],
                "fehler": None, "ocr_cache": {}, "modell": self.modell, "nebenkanaele": self.nebenkanaele}

    def schwaerze_pdf(self, pdf, funde, melde=None, ocr=None, ocr_cache=None, ziel_ordner=None, modell=None,
                      freigabe_erforderlich=False, profil="hoch", nebenkanaele=None):
        self.schwaerz_aufrufe.append({"funde": [dict(f) for f in funde], "ocr": ocr, "ocr_cache": ocr_cache,
                                      "ziel_ordner": ziel_ordner, "modell": modell, "nebenkanaele": nebenkanaele,
                                      "freigabe_erforderlich": freigabe_erforderlich, "profil": profil})
        self._nr += 1
        ziel = Path(ziel_ordner) / f"anonym_{self._nr:02d}{'_PRUEFEN' if freigabe_erforderlich else ''}.pdf"
        with fitz.open(pdf) as doc:
            for seite in doc:
                for f in funde:
                    for r in seite.search_for(f["text"]):
                        seite.add_redact_annot(r, fill=(0, 0, 0))
                seite.apply_redactions()
            doc.save(ziel, garbage=4, deflate=True)          # ohne die alten Inhaltsströme (Kanal rohdaten)
        return {"ausgabe": ziel, "treffer": len(funde), "status": "pruefen" if freigabe_erforderlich else "fertig",
                "verdacht": [], "reste": [], "warnungen": [], "fehler": None, "stellen_nicht_lokalisiert": 0,
                "pruefen_gruende": ["Freigabe ausstehend"] if freigabe_erforderlich else []}


def _eintrag(ergebnis: dict, eid: str) -> dict:
    (d,) = ergebnis["dokumente"]
    return next(e for e in d["eintraege"] if e["id"] == eid)


def test_angebotener_fund_geht_nur_im_weg_engine_an_die_schwaerzung(tmp_path):
    """Der nur angebotene Fund (Diagnose, Stelle abgewählt) steht im Weg engine im Auftrag – eine Schwärzung, die jeden
    übergebenen Fund schwärzt, entfernt ihn dort –, im Weg oberflaeche fehlt er wie im Auftrag der Oberfläche und bleibt
    lesbar. Weg engine ruft Analyse und Schwärzung genau wie bisher auf; Weg oberflaeche mit Schutzstufe, eigenem
    LaufWissen, Seitenmodell, Nebenkanälen und Freigabe. Der Weg steht in ergebnis.json und bericht.md."""
    korpus = _mini_korpus(tmp_path / "korpus").parent
    engine = _JederFundEngine()
    e = bewertung.bewerte_korpus(korpus, tmp_path / "engine", cli_ocr=False, melde=None, pipeline=engine)
    (a,), (s,) = engine.analyse_aufrufe, engine.schwaerz_aufrufe
    assert a == {"aktive": STANDARD_AN, "nie": [], "immer": [], "ocr": None, "profil": "hoch", "lauf": None}
    assert [f["text"] for f in s["funde"]] == [NAME, DIAGNOSE]               # jeder Fund, so wie analysiert
    assert s["modell"] is None and s["nebenkanaele"] is None and s["freigabe_erforderlich"] is False
    assert _eintrag(e, "e2")["status"] == "entfernt" and e["gesamt"]["recall_erweitert"] == 1.0
    assert e["weg"] == "engine" and e["einstellungen"]["alle_funde_angehakt"] is True
    assert "ausgaben_nur_freigabe" not in e["restrisiko"]
    assert "Weg der Schwärzung: **engine**" in (tmp_path / "engine" / "bericht.md").read_text(encoding="utf-8")

    oberflaeche = _JederFundEngine()
    o = bewertung.bewerte_korpus(korpus, tmp_path / "oberflaeche", cli_ocr=False, melde=None, pipeline=oberflaeche,
                                 weg="oberflaeche")
    (a,), (s,) = oberflaeche.analyse_aufrufe, oberflaeche.schwaerz_aufrufe
    assert a["aktive"] == auftrag.standard_kategorien() and a["profil"] == "hoch" and isinstance(a["lauf"], _Lauf)
    assert [f["text"] for f in s["funde"]] == [NAME]                         # der angebotene Fund fehlt
    assert s["modell"] is oberflaeche.modell and s["nebenkanaele"] == oberflaeche.nebenkanaele
    assert s["freigabe_erforderlich"] is True and s["profil"] == "hoch" and s["ocr_cache"] == {}
    assert _eintrag(o, "e2")["status"] == "leck" and o["gesamt"]["recall_erweitert"] == 0.0
    assert _eintrag(o, "e1")["status"] == _eintrag(e, "e1")["status"] == "entfernt"
    assert _eintrag(o, "e3")["status"] == _eintrag(e, "e3")["status"]
    (d,) = o["dokumente"]
    assert [(f["text"], f["zustand"], f["aktiv"]) for f in d["funde"]] == [(NAME, "an", True),
                                                                          (DIAGNOSE, "aus", False)]
    assert d["status_ausgabe"] == "pruefen" and d["freigabe_ausstehend"] and d["auftrag_funde"] == 1
    rr = o["restrisiko"]
    assert rr["ausgaben_nur_freigabe"] == 1 and rr["ausgaben_pruefen"] == 0     # nur die Freigabe: kein Grund
    assert o["weg"] == "oberflaeche" and o["einstellungen"]["alle_funde_angehakt"] is False
    assert o["einstellungen"]["schutzstufe"] == "hoch" and o["einstellungen"]["freigabe_vor_weitergabe"] is True
    bericht = (tmp_path / "oberflaeche" / "bericht.md").read_text(encoding="utf-8")
    assert "Weg der Schwärzung: **oberflaeche**" in bericht and "nur wegen „Freigabe vor Weitergabe“" in bericht
    gespeichert = json.loads((tmp_path / "oberflaeche" / "ergebnis.json").read_text(encoding="utf-8"))
    assert gespeichert["weg"] == "oberflaeche"


def test_weg_oberflaeche_braucht_den_auftrag_des_programms(tmp_path):
    """Ohne anonymisierer/auftrag.py (ältere Programmversion) bricht der Weg oberflaeche vor dem ersten Dokument ab –
    ein Nachbau der Auswahl im Benchmark könnte still von der Oberfläche abweichen. Unbekannte Wege sind ein Fehler."""
    korpus = _mini_korpus(tmp_path / "korpus").parent
    with pytest.raises(RuntimeError, match="auftrag.py"):
        bewertung.bewerte_korpus(korpus, tmp_path / "a", melde=None, pipeline=bewertung.NullAnonymisierer(),
                                 weg="oberflaeche")
    assert not (tmp_path / "a").exists()                       # nichts angelegt, kein Dokument bewertet
    with pytest.raises(ValueError, match="unbekannter Weg"):
        bewertung.bewerte_korpus(korpus, tmp_path / "b", melde=None, pipeline=_JederFundEngine(), weg="gui")
    cli = _benchmark_cli()
    for argumente in (["--weg", "gui"], ["--weg", "oberflaeche", "--selbstpruefung"]):
        with pytest.raises(SystemExit):
            cli.main(["--korpus", str(korpus), "--ausgabe", str(tmp_path / "c")] + argumente)
    assert not (tmp_path / "c").exists()


# ----------------------------------------------------------------------
# Echte Engine: Weg engine unverändert, Weg oberflaeche mit dem Auftrag der Oberfläche
# ----------------------------------------------------------------------
def _mitschnitt(funktion, aufrufe: list):
    """Ruft die echte Funktion und schneidet Argumente mit; functools.wraps erhält die Signatur (kann, _rufe)."""
    @functools.wraps(funktion)
    def mit(*args, **kwargs):
        ergebnis = funktion(*args, **kwargs)
        aufrufe.append({"args": args, "kwargs": kwargs, "ergebnis": ergebnis})
        return ergebnis
    return mit


@pytest.fixture(scope="module")
def mini_ci_korpus(tmp_path_factory):
    """Antrag (Formular) und Arztbrief des CI-Korpus (Seed 1): beide mit in „Hoch“ nur angebotenen Gesundheitsdaten."""
    ordner = tmp_path_factory.mktemp("weg") / "korpus"
    ordner.mkdir()
    plaene = generator.plane_korpus(5, 1)
    for plan in (plaene[3], plaene[4]):
        generator.erzeuge_dokument(plan, 1, ordner)
    return ordner


# Form des Ergebnisses vor dem Weg oberflaeche (Stand 7a3f8a3) – im Weg engine kommt nur „weg“ hinzu
SCHLUESSEL_ERGEBNIS = {"schema", "erzeugt", "korpus", "repo", "commit", "umgebung", "einstellungen",
                       "laufzeit_gesamt_s", "gesamt", "je_kategorie", "je_merkmal", "je_kanal", "je_typ", "je_hinweis",
                       "diagnosen", "laufzeit", "restrisiko", "lecks", "ueberschwaerzt", "dokumente"}
SCHLUESSEL_DOKUMENT = {"dokument", "typ", "merkmale", "seiten", "fehler", "warnungen", "ausgabe", "keine_ausgabe",
                       "dauer_analyse_s", "dauer_schwaerzung_s", "funde_anzahl", "treffer", "reste",
                       "ocr_seiten_programm", "status_ausgabe", "verdacht", "reste_verdacht", "dauer_restrisiko_s",
                       "eintraege", "fehlalarme", "dauer_bewertung_s", "funde", "funde_aktiv", "ocr_seiten_bewertung",
                       "pixel_seiten", "platzhalter_entfernt"}


@braucht_modell
@braucht_ocr
def test_echte_engine_weg_engine_unveraendert_weg_oberflaeche_wie_die_oberflaeche(mini_ci_korpus, tmp_path):
    """Weg engine (Standard, ohne Angabe): Analyse mit den standardmäßig angehakten Kategorien, leeren Listen und dem
    OCR-Dienst – sonst nichts; Schwärzung mit genau den Funden der Analyse (dieselben Objekte), ocr, ocr_cache und
    ziel_ordner – sonst nichts; Ergebnis in derselben Form wie vor dem Weg oberflaeche (nur „weg“ kommt hinzu).
    Weg oberflaeche auf denselben Dokumenten: eigenes LaufWissen je Dokument, die nur angebotenen Gesundheitsdaten
    fehlen im Auftrag, Seitenmodell/Nebenkanäle der Analyse und die Freigabe gehen mit. Die echte Engine schwärzt nur
    Stellen mit „an“: die angebotenen Diagnosen bleiben in BEIDEN Wegen lesbar – Recall, Über-Schwärzung und
    Fehlalarme gleich."""
    ergebnisse = {}
    for weg in ("engine", "oberflaeche"):
        pipeline = bewertung.Pipeline()
        analysen, schwaerzungen = [], []
        pipeline.analysiere_pdf = _mitschnitt(pipeline.analysiere_pdf, analysen)
        pipeline.schwaerze_pdf = _mitschnitt(pipeline.schwaerze_pdf, schwaerzungen)
        zusatz = {} if weg == "engine" else {"weg": weg}
        ergebnisse[weg] = bewertung.bewerte_korpus(mini_ci_korpus, tmp_path / weg, cli_ocr=False, melde=None,
                                                   pipeline=pipeline, **zusatz)
        assert len(analysen) == len(schwaerzungen) == 2
        for a, s in zip(analysen, schwaerzungen):
            funde = a["ergebnis"]["funde"]
            angeboten = [f for f in funde if f.get("stellen") and not any(st.get("an", True) for st in f["stellen"])]
            assert any(f["kategorie"] in muster.GESUNDHEIT for f in angeboten), [f["kategorie"] for f in funde]
            assert s["args"][0] == a["args"][0]
            if weg == "engine":
                assert a["args"][1:] == (STANDARD_AN, [], []) and set(a["kwargs"]) == {"ocr"}
                assert len(s["args"]) == 2 and len(s["args"][1]) == len(funde)
                assert all(x is y for x, y in zip(s["args"][1], funde))
                assert set(s["kwargs"]) == {"ocr", "ocr_cache", "ziel_ordner"}
                assert s["kwargs"]["ocr_cache"] is a["ergebnis"]["ocr_cache"]
            else:
                assert a["args"][1:] == (auftrag.standard_kategorien(), [], [])
                assert set(a["kwargs"]) == {"ocr", "profil", "lauf"} and a["kwargs"]["profil"] == "hoch"
                assert isinstance(a["kwargs"]["lauf"], pipeline.lauf_wissen)
                ids = [f["id"] for f in s["args"][1]]
                bilder = [f["id"] for f in angeboten if any("bereich" in st for st in f["stellen"])]
                assert ids == [f["id"] for f in funde if f not in angeboten] + bilder   # angebotene Texte fehlen
                assert set(s["kwargs"]) == {"ocr", "ziel_ordner", "ocr_cache", "modell", "nebenkanaele",
                                            "freigabe_erforderlich", "profil"}
                assert s["kwargs"]["modell"] is a["ergebnis"]["modell"]
                assert s["kwargs"]["freigabe_erforderlich"] is True and s["kwargs"]["profil"] == "hoch"
                assert s["ergebnis"]["ausgabe"].name.endswith("_PRUEFEN.pdf")
        if weg == "oberflaeche":
            assert analysen[0]["kwargs"]["lauf"] is not analysen[1]["kwargs"]["lauf"]    # je Dokument ein Lauf
    e, o = ergebnisse["engine"], ergebnisse["oberflaeche"]
    assert set(e) == SCHLUESSEL_ERGEBNIS | {"weg"} and e["weg"] == "engine"
    assert list(e["einstellungen"]) == ["aktive_kategorien", "nie_liste", "immer_liste", "alle_funde_angehakt",
                                        "pixel_schwelle", "ocr_dpi_bewertung"]
    assert e["einstellungen"]["aktive_kategorien"] == sorted(STANDARD_AN)
    assert all(set(d) == SCHLUESSEL_DOKUMENT for d in e["dokumente"])
    assert all(set(f) == {"kategorie", "text", "seiten", "aktiv"} for d in e["dokumente"] for f in d["funde"])
    assert "ausgaben_nur_freigabe" not in e["restrisiko"]
    for schluessel in ("recall_kern", "recall_erweitert", "ueberschwaerzung", "fehlalarme", "funde_aktiv", "funde"):
        assert e["gesamt"][schluessel] == o["gesamt"][schluessel], schluessel
    diagnosen = [(d["dokument"], x["id"], x["status"]) for d in e["dokumente"] for x in d["eintraege"]
                 if x["kategorie"] in muster.GESUNDHEIT and x["erwartung"] == "schwaerzen"]
    assert diagnosen and all(status != "entfernt" for _, _, status in diagnosen)       # angeboten: bleibt lesbar
    assert diagnosen == [(d["dokument"], x["id"], x["status"]) for d in o["dokumente"] for x in d["eintraege"]
                         if x["kategorie"] in muster.GESUNDHEIT and x["erwartung"] == "schwaerzen"]
    assert all(d["status_ausgabe"] == "pruefen" for d in o["dokumente"])               # Freigabe vor Weitergabe
    assert o["restrisiko"]["ausgaben_nur_freigabe"] == sum(d["freigabe_ausstehend"] for d in o["dokumente"])
    assert o["restrisiko"]["ausgaben_pruefen"] + o["restrisiko"]["ausgaben_nur_freigabe"] == len(o["dokumente"])


# ----------------------------------------------------------------------
# Oberfläche und Benchmark: dieselben Einstellungen, derselbe Auftrag (unter Xvfb)
# ----------------------------------------------------------------------
@braucht_modell
@pytest.mark.skipif(KEIN_DISPLAY, reason="kein Display (DISPLAY nicht gesetzt)")
def test_oberflaeche_und_benchmark_schicken_denselben_auftrag(app, umgebung, dialoge, monkeypatch):
    """Frisch gestartete Oberfläche (keine gespeicherten Einstellungen), Arztbericht mit angebotenen Gesundheitsdaten:
    Analyse mit denselben Einstellungen wie der Weg oberflaeche, Häkchen der Fundliste = standard_zustand, und beim
    Schwärzen gehen dieselben Funde mit denselben Parametern an die Engine wie im Benchmark (bewerte_dokument, Weg
    oberflaeche) für dasselbe Analyseergebnis."""
    from anonymisierer import gui, schwaerzung

    gui_analysen, gui_schwaerzungen = [], []
    monkeypatch.setattr(gui, "analysiere_pdf", _mitschnitt(gui.analysiere_pdf, gui_analysen))
    monkeypatch.setattr(gui, "schwaerze_pdf", _mitschnitt(schwaerzung.schwaerze_pdf, gui_schwaerzungen))
    # Einstellungen beim ersten Start = Einstellungen des Wegs oberflaeche
    assert app._aktive_kategorien() == auftrag.standard_kategorien()
    assert app.basis_profil == app.profil_var.get() == auftrag.STANDARD_PROFIL
    assert app.freigabe_var.get() is auftrag.STANDARD_FREIGABE
    pdf = pdf_schreiben(Path(umgebung["tmp"]) / "Kunde" / "Arztbericht.pdf", ARZTBERICHT)
    app._pdfs_hinzufuegen([str(pdf)])
    starte_lauf(app, app.analysieren, timeout=120)
    ergebnis = app.analyse_ergebnisse[pdf]
    (a,) = gui_analysen
    assert a["args"][1:] == (auftrag.standard_kategorien(), [], [])
    assert a["kwargs"]["profil"] == auftrag.STANDARD_PROFIL and a["kwargs"].get("kundenliste") is None
    # Häkchen der Fundliste nach der Analyse = standard_zustand; Auftrag der Oberfläche = Auftrag des Benchmarks
    benchmark_auftrag, zustaende = auftrag.standard_auftrag(ergebnis, gui.schwaerze_pdf)
    assert zustaende == [app.fund_zustand(pdf, i) for i in range(len(ergebnis["funde"]))]
    assert zustaende == [app._zustand(f"{pdf}::{i}") for i in range(len(ergebnis["funde"]))]
    assert "aus" in zustaende and "an" in zustaende                   # angebotene Gesundheitsdaten, IBAN
    gui_auftrag = app._auftrag(pdf)
    for schluessel in ("funde", "ocr_cache", "bereiche", "stellen", "nebenkanaele", "ohne_haken", "gefunden"):
        assert gui_auftrag[schluessel] == benchmark_auftrag[schluessel], schluessel
    assert gui_auftrag["modell"] is benchmark_auftrag["modell"] is ergebnis["modell"]
    dialoge.antwort = False
    starte_lauf(app, app.schwaerzen, timeout=120)
    (g,) = gui_schwaerzungen
    assert app.ausgaben[pdf]["status"] == "pruefen"

    # derselbe Auftrag über den Benchmark (bewerte_dokument, Weg oberflaeche) für dasselbe Analyseergebnis
    class _GleicheAnalyse(bewertung.NullAnonymisierer):
        lauf_wissen = None

        def analysiere_pdf(self, pdf_pfad, aktive, nie, immer, ocr=None, profil="hoch", lauf=None):
            self.analyse = {"aktive": set(aktive), "nie": nie, "immer": immer, "profil": profil}
            return ergebnis
    pipeline = _GleicheAnalyse()
    pipeline.auftrag = auftrag
    benchmark_schwaerzungen = []
    pipeline.schwaerze_pdf = _mitschnitt(schwaerzung.schwaerze_pdf, benchmark_schwaerzungen)
    wahrheit = {"dokument": pdf.name, "seiten": 1, "eintraege": []}
    ziel = Path(umgebung["tmp"]) / "benchmark"
    ziel.mkdir()
    bewertung.bewerte_dokument(pdf, wahrheit, pipeline, FakeOcr(), ziel, Path(umgebung["tmp"]), cli_ocr=False,
                               weg="oberflaeche")
    assert pipeline.analyse == {"aktive": set(a["args"][1]), "nie": a["args"][2], "immer": a["args"][3],
                                "profil": a["kwargs"]["profil"]}
    (b,) = benchmark_schwaerzungen
    assert b["args"][1] == g["args"][1] == benchmark_auftrag["funde"]
    nur_gui = {"melde", "fortschritt", "abbruch", "ocr", "ziel_ordner"}
    assert set(g["kwargs"]) - nur_gui == set(b["kwargs"]) - {"ocr", "ziel_ordner"}
    for schluessel in set(b["kwargs"]) - {"ocr", "ziel_ordner"}:
        assert b["kwargs"][schluessel] is g["kwargs"][schluessel] or b["kwargs"][schluessel] == g["kwargs"][
            schluessel], schluessel
    assert b["kwargs"]["freigabe_erforderlich"] is True and b["kwargs"]["modell"] is ergebnis["modell"]

"""Selbsttest mit ECHTEN Dokumenten – ausschließlich Zählwerte, nie Inhalte.

Für den Makler: Wie zuverlässig arbeitet das Programm mit den eigenen Unterlagen, ohne dass dabei irgendein
Inhalt (Name, Nummer, Dateiname, Ordnername) auf dem Bildschirm, in einer Datei oder in einem Protokoll landet?

Aufruf (aus der Projektwurzel):
    python werkzeuge/selbsttest.py <ordner> [--profil hoch] [--behalten <ordner>] [--einstellungen]
                                            [--kategorien iban,email,...]

Ablauf: Alle PDFs im Ordner (auch in Unterordnern, ohne bereits anonymisierte Ausgaben) werden wie in der
Oberfläche analysiert und geschwärzt – in einen temporären Ordner, der danach gelöscht wird (außer mit
--behalten <ordner>: dann liegen die Ausgaben dort, wie bei normaler Benutzung, samt _zuordnung.txt).

Ausgegeben werden NUR Zählwerte: Dokumente (als laufende Nummer, ohne Dateinamen), Seiten, OCR-Seiten, Funde je
Kategorie, Verdachtsstellen je Dokument und je Regel, wie viele Ausgaben _PRUEFEN sind, Meldungs-Codes, Fehlerarten
(nur der Typ, nie der Text) und Laufzeiten. Fundtexte, Warnungstexte, Dateinamen und Pfade werden nie ausgegeben.

Optionen:
    --profil        Schutzstufe: ausgewogen | hoch (Standard) | maximal
    --behalten      Ausgaben in diesen Ordner schreiben und behalten (sonst temporär, danach gelöscht)
    --einstellungen NIE-/IMMER-Liste aus den gespeicherten Einstellungen der Oberfläche verwenden
    --kategorien    nur diese Kategorien (Komma-Liste) statt der Schutzstufe
"""

from __future__ import annotations

import argparse
import contextlib
import inspect
import io
import multiprocessing
import re
import shutil
import sys
import tempfile
import time
import warnings
from collections import Counter
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent

# Regelgruppen der Verdachtsstellen (Grund ohne »…«-Zusatz, der ein Etikett aus dem Dokument enthalten könnte)
_REGEL_RE = re.compile(r"\s*»[^«]*«")


def _regel(grund: str) -> str:
    return _REGEL_RE.sub("", str(grund or "")).strip() or "unbekannt"


def _rufe(funktion, *args, **kwargs):
    """Unbekannte Schlüsselwort-Argumente weglassen (ältere Programmversionen)."""
    try:
        parameter = inspect.signature(funktion).parameters
    except (TypeError, ValueError):
        return funktion(*args, **kwargs)
    if any(p.kind is p.VAR_KEYWORD for p in parameter.values()):
        return funktion(*args, **kwargs)
    return funktion(*args, **{k: v for k, v in kwargs.items() if k in parameter})


def _kategorien(profil: str, nur: str | None) -> set:
    from anonymisierer import gui_attrappen, muster

    alle = {k[0] for k in muster.KATEGORIEN}
    if nur:
        return {k.strip() for k in nur.split(",") if k.strip()} & alle
    profile = getattr(muster, "PROFILE", None) or gui_attrappen.PROFILE
    menge = gui_attrappen.profil_kategorien(profile, profil, alle)
    if menge is None:
        menge = gui_attrappen.profil_kategorien(gui_attrappen.PROFILE, profil, alle)
    return set(menge or {k[0] for k in muster.KATEGORIEN if k[4]})


def _feld(v, name, standard=None):
    return v.get(name, standard) if isinstance(v, dict) else getattr(v, name, standard)


def selbsttest(ordner: Path, profil: str = "hoch", behalten: Path | None = None, einstellungen: bool = False,
               kategorien: str | None = None, ausgabe=print) -> dict:
    """Führt den Selbsttest aus und liefert die Zählwerte (dict); `ausgabe` erhält nur Zählzeilen."""
    from anonymisierer import dateien
    from anonymisierer.analyse import analysiere_pdf
    from anonymisierer.schwaerzung import schwaerze_pdf

    try:
        from anonymisierer.ocr import OcrDienst
    except ImportError:
        OcrDienst = None

    aktive = _kategorien(profil, kategorien)
    nie, immer = [], []
    if einstellungen:
        gespeichert = dateien.einstellungen_laden() or {}
        nie = [str(x) for x in gespeichert.get("nie") or [] if str(x).strip()]
        immer = [str(x) for x in gespeichert.get("immer") or [] if str(x).strip()]
    pdfs = dateien.sammle_pdfs([ordner])
    ziel = Path(behalten) if behalten else Path(tempfile.mkdtemp(prefix="selbsttest_"))
    if behalten:
        ziel.mkdir(parents=True, exist_ok=True)
    werte = {"dokumente": len(pdfs), "seiten": 0, "ocr_seiten": 0, "funde": Counter(), "fund_stellen": 0,
             "verdacht_je_dokument": [], "verdacht_je_regel": Counter(), "pruefen": 0, "fertig": 0,
             "ohne_ausgabe": 0, "fehler": Counter(), "meldungen": Counter(), "analyse_s": 0.0,
             "schwaerzung_s": 0.0, "restrisiko_s": 0.0}
    ausgabe("Selbsttest PDF-Anonymisierer – es werden nur Zählwerte ausgegeben, keine Inhalte und keine "
            "Dateinamen.")
    ausgabe(f"Schutzstufe: {profil}" + (" (eigene Kategorienauswahl)" if kategorien else "")
            + f" · {len(aktive)} Kategorien · NIE-Liste: {len(nie)} · IMMER-Liste: {len(immer)} Einträge")
    ausgabe(f"Gefunden: {len(pdfs)} PDF-Datei(en)")
    beginn = time.perf_counter()
    dienst = None
    if OcrDienst is not None:
        try:
            dienst = OcrDienst()
        except Exception:
            dienst = None
    try:
        for nr, pdf in enumerate(pdfs, 1):
            t0 = time.perf_counter()
            # stdout/stderr der Bibliotheken während der Verarbeitung abfangen: dort könnte Text stehen
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                try:
                    a = _rufe(analysiere_pdf, pdf, aktive, nie, immer, ocr=dienst, profil=profil)
                except Exception as e:                                   # nur die Art des Fehlers zählen
                    a = {"fehler": f"Analyse: {type(e).__name__}", "funde": []}
                t1 = time.perf_counter()
                e = {}
                if not a.get("fehler") and a.get("funde"):
                    try:
                        e = _rufe(schwaerze_pdf, pdf, a["funde"], ocr=dienst, ocr_cache=a.get("ocr_cache"),
                                  ziel_ordner=ziel, modell=a.get("modell"), profil=profil)
                    except Exception as fehler:
                        e = {"fehler": f"Schwärzung: {type(fehler).__name__}"}
            t2 = time.perf_counter()
            werte["analyse_s"] += t1 - t0
            werte["schwaerzung_s"] += t2 - t1
            werte["restrisiko_s"] += float(e.get("dauer_restrisiko_s") or 0.0)
            seiten = int(a.get("seiten") or 0)
            werte["seiten"] += seiten
            werte["ocr_seiten"] += int(a.get("ocr_seiten") or 0)
            for f in a.get("funde") or []:
                werte["funde"][f.get("kategorie") or "?"] += 1
                werte["fund_stellen"] += int(f.get("anzahl") or len(f.get("stellen") or []) or 1)
            for m in list(a.get("meldungen") or []) + list(e.get("meldungen") or []):
                if isinstance(m, dict) and m.get("code"):
                    werte["meldungen"][str(m["code"])] += 1
            fehler = a.get("fehler") or e.get("fehler")
            verdacht = list(e.get("verdacht") or [])
            for v in verdacht:
                werte["verdacht_je_regel"][_regel(_feld(v, "grund", ""))] += 1
            werte["verdacht_je_dokument"].append(len(verdacht))
            if fehler:
                art = "Abgebrochen" if fehler == "Abgebrochen" else (
                    fehler.split(":")[0] if fehler.startswith(("Analyse", "Schwärzung")) else "Programmmeldung")
                werte["fehler"][art] += 1
                status = "Fehler"
            elif not e.get("ausgabe"):
                werte["ohne_ausgabe"] += 1
                status = "keine Ausgabe (kein Fund)"
            elif e.get("status") == "pruefen" or "_PRUEFEN" in Path(str(e.get("ausgabe"))).name.upper():
                werte["pruefen"] += 1
                status = "_PRUEFEN"
            else:
                werte["fertig"] += 1
                status = "fertig"
            ausgabe(f"Dokument {nr:3d}: {seiten} Seite(n), {int(a.get('ocr_seiten') or 0)} per OCR, "
                    f"{len(a.get('funde') or [])} Funde, {len(verdacht)} Verdachtsstelle(n), {status}, "
                    f"{t2 - t0:.1f} s")
    finally:
        if dienst is not None:
            try:
                dienst.schliessen()
            except Exception:
                pass
        if not behalten:
            shutil.rmtree(ziel, ignore_errors=True)
    gesamt = time.perf_counter() - beginn
    werte["laufzeit_s"] = gesamt
    seiten = werte["seiten"] or 1
    ausgabe("")
    ausgabe(f"Dokumente: {werte['dokumente']} · Seiten: {werte['seiten']} · davon per OCR gelesen: "
            f"{werte['ocr_seiten']}")
    ausgabe("Funde je Kategorie: " + (", ".join(f"{k} {v}" for k, v in sorted(werte["funde"].items())) or "keine")
            + f" (zusammen {sum(werte['funde'].values())} Funde an {werte['fund_stellen']} Stellen)")
    mit_verdacht = sum(1 for n in werte["verdacht_je_dokument"] if n)
    ausgabe(f"Verdachtsstellen: {sum(werte['verdacht_je_dokument'])} in {mit_verdacht} Dokument(en); "
            f"je Dokument: {', '.join(str(n) for n in werte['verdacht_je_dokument']) or '–'}")
    if werte["verdacht_je_regel"]:
        ausgabe("Verdacht je Regel: " + ", ".join(f"{k} {v}" for k, v in werte["verdacht_je_regel"].most_common()))
    ausgabe(f"Ausgaben: {werte['pruefen']} _PRUEFEN, {werte['fertig']} fertig, {werte['ohne_ausgabe']} ohne Ausgabe")
    if werte["meldungen"]:
        ausgabe("Meldungen: " + ", ".join(f"{k} {v}" for k, v in sorted(werte["meldungen"].items())))
    ausgabe("Fehler: " + (", ".join(f"{k} {v}" for k, v in werte["fehler"].items()) or "keine"))
    ausgabe(f"Laufzeit: Analyse {werte['analyse_s']:.1f} s, Schwärzung {werte['schwaerzung_s']:.1f} s "
            f"(davon Restrisiko-Prüfung {werte['restrisiko_s']:.1f} s), gesamt {gesamt:.1f} s, "
            f"{gesamt / seiten:.2f} s je Seite")
    ausgabe("Ausgaben behalten (im angegebenen Ordner)." if behalten else "Temporäre Ausgaben wurden gelöscht.")
    return werte


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Selbsttest mit echten Dokumenten – nur Zählwerte, keine Inhalte")
    parser.add_argument("ordner", type=Path, help="Ordner mit PDF-Dateien (auch Unterordner)")
    parser.add_argument("--profil", default="hoch", choices=("ausgewogen", "hoch", "maximal"), help="Schutzstufe")
    parser.add_argument("--behalten", type=Path, default=None, help="Ausgaben in diesem Ordner behalten")
    parser.add_argument("--einstellungen", action="store_true",
                        help="NIE-/IMMER-Liste aus den gespeicherten Einstellungen verwenden")
    parser.add_argument("--kategorien", default=None, help="nur diese Kategorien (Komma-Liste)")
    args = parser.parse_args(argv)
    warnings.filterwarnings("ignore")
    if str(WURZEL) not in sys.path:
        sys.path.insert(0, str(WURZEL))
    if not args.ordner.is_dir():
        print("Ordner nicht gefunden.")
        return 2
    selbsttest(args.ordner, args.profil, args.behalten, args.einstellungen, args.kategorien)
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())

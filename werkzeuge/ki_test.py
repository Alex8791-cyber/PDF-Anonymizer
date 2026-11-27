"""KI-Verbindung prüfen: Läuft LM Studio, welches Modell ist geladen, wie schnell und wie gut antwortet es?

Nur mit erfundenen Beispieldaten – kein echtes Dokument, keine Datei wird gelesen oder geschrieben.

Aufruf (aus der Projektwurzel):   python werkzeuge/ki_test.py [--url http://127.0.0.1:1234]
Unter Windows: KI-testen.bat doppelklicken.

Rückgabe: 0 = alles in Ordnung, 1 = LM Studio nicht erreichbar oder kein Modell geladen (oder unzulässige Adresse),
2 = das Modell antwortet, aber unbrauchbar (kein JSON, Beispielwerte nicht erkannt).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
if str(WURZEL) not in sys.path:
    sys.path.insert(0, str(WURZEL))

from anonymisierer import ki  # noqa: E402

# erfundene Werte (keine echte Person, gültige Beispiel-IBAN aus der Bankdokumentation)
BEISPIEL = ("Sehr geehrter Herr Quirin Sedlbauer,\n"
            "wir bestätigen den Eingang Ihrer Schadenmeldung zum Vertrag KV-2024-88812.\n"
            "Bitte überweisen Sie den Eigenanteil auf IBAN DE89 3704 0044 0532 0130 00.\n"
            "Bei starkem Regen lief Wasser in den Keller.\n"
            "Mit freundlichen Grüßen\nAlpenland Versicherung AG")
ERWARTET = ("Quirin Sedlbauer", "KV-2024-88812", "DE89 3704 0044 0532 0130 00")


def _flach(text: str) -> str:
    return "".join(str(text).split()).casefold()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="LM-Studio-Verbindung der KI-Zweitprüfung testen "
                                                 "(nur erfundene Beispieldaten).")
    parser.add_argument("--url", default=None, help="Adresse von LM Studio auf diesem Rechner "
                                                    "(Vorgabe: PDFA_KI_URL oder http://127.0.0.1:1234)")
    args = parser.parse_args(argv)
    try:
        url = ki.basis_url(args.url)
    except ValueError as e:
        print(f"✗ {e}")
        return 1
    print(f"Adresse: {url} (nur dieser Rechner)")
    modell = ki.geladenes_modell(url)
    if modell is None:
        print("✗ LM Studio ist nicht erreichbar oder es ist kein Modell geladen.\n"
              "  Bitte LM Studio starten, ein Modell laden und den Server einschalten\n"
              "  (Reiter „Developer“ → „Start Server“, Port 1234).")
        return 1
    print(f"✓ Geladenes Modell: {modell.kennung}" + (" (kann auch Bilder lesen)" if modell.bild else ""))
    dienst = ki.Dienst(url)
    beginn = time.perf_counter()
    try:
        funde = dienst.personendaten(BEISPIEL)
    except ki.KiFehler as e:
        print(f"✗ Antwort unbrauchbar: {e}")
        return 2
    dauer = time.perf_counter() - beginn
    print(f"  Antwortzeit Erkennung: {dauer:.1f} s für {len(BEISPIEL)} Zeichen "
          f"(eine Briefseite hat etwa 2.000–3.000 Zeichen)")
    for f in funde:
        print(f"  {'✓' if f['sicher'] else '?'} {f['art']}: {f['text']}")
    sicher = {_flach(f["text"]) for f in funde if f["sicher"]}
    fehlt = [w for w in ERWARTET if not any(_flach(w) in s or s in _flach(w) for s in sicher)]
    beginn = time.perf_counter()
    try:
        urteil = dienst.urteile([("Regen", "Bei starkem Regen lief Wasser in den Keller.", "möglicher Name")])[0]
    except ki.KiFehler as e:
        print(f"✗ Urteil unbrauchbar: {e}")
        return 2
    print(f"  Urteil zu „Regen“ im Satz über das Wetter: {urteil} (richtig: nein) – "
          f"{time.perf_counter() - beginn:.1f} s")
    if fehlt:
        print("✗ Nicht erkannt: " + ", ".join(fehlt) + " – das Modell eignet sich nur eingeschränkt.")
        return 2
    if urteil == "ja":
        print("✗ Das Modell hält das Wetterwort für einen Namen – für die Verdachtsprüfung ungeeignet.")
        return 2
    print("✓ Die KI-Zweitprüfung ist einsatzbereit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

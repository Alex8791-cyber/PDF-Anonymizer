"""Detektor-Register in der EXE: die Rückfallliste _BEKANNTE_MODULE bleibt deckungsgleich mit dem Paketordner.

anonymisierer/detektoren/__init__.py lädt alle Module des Pakets über pkgutil.iter_modules und ergänzt jedes Modul
aus _BEKANNTE_MODULE, das diese Liste nicht nennt. In einer EXE kann iter_modules leer bleiben (Packer ohne
passenden Laufzeit-Hook) – dann trägt allein die Rückfallliste. Stand dort ein Modul nicht, liefe die EXE still ohne
dessen Erkennungsregeln (bis Phase 3 stand dort nur "klassisch"). Fehlt ein Modul im Bundle ganz (PyInstaller ohne
--collect-submodules anonymisierer.detektoren: 8 von 10 Modulen, EXE-Probe), kann keine Liste es retten – dann muss
die Analyse es melden, statt still weniger zu finden.
Diese Tests prüfen die Liste gegen den Ordner und spielen beide EXE-Fälle in einem eigenen Prozess durch, damit
das globale Register dieses Testlaufs unberührt bleibt.
"""

import json
import pkgutil
import subprocess
import sys
from pathlib import Path

from anonymisierer import detektoren

ORDNER = Path(detektoren.__file__).resolve().parent
WURZEL = ORDNER.parent.parent

# Lädt das Detektor-Paket in einem frischen Prozess und gibt Register, geladene Module und Ladefehler als JSON aus.
# "exe": pkgutil.iter_modules liefert nichts (wie in einer EXE ohne Modulliste);
# "exe_luecke": zusätzlich fehlt ein Modul (wie in einer unvollständig gebauten EXE).
_LADEN = r"""
import json, pkgutil, sys
sys.path.insert(0, sys.argv[1])
modus = sys.argv[2]
if modus in ("exe", "exe_luecke"):
    pkgutil.iter_modules = lambda *a, **k: iter(())
if modus == "exe_luecke":
    import importlib.abc

    class Fehlt(importlib.abc.MetaPathFinder):
        def find_spec(self, name, pfad=None, ziel=None):
            if name == "anonymisierer.detektoren.struktur_formular":
                raise ModuleNotFoundError(f"No module named {name!r}", name=name)
            return None
    sys.meta_path.insert(0, Fehlt())
from anonymisierer import detektoren
print(json.dumps({"register": [[e.name, e.funktion.__module__, e.funktion.__qualname__] for e in detektoren.REGISTER],
                  "module": sorted(n for n in sys.modules if n.startswith("anonymisierer.detektoren.")),
                  "ladefehler": detektoren.LADEFEHLER}))
"""


def _laden(modus: str) -> dict:
    erg = subprocess.run([sys.executable, "-W", "ignore", "-c", _LADEN, str(WURZEL), modus], capture_output=True,
                         text=True, encoding="utf-8", timeout=300)
    assert erg.returncode == 0, erg.stderr
    return json.loads(erg.stdout.strip().splitlines()[-1])


def test_rueckfallliste_nennt_genau_die_module_im_paketordner():
    im_ordner = {m.name for m in pkgutil.iter_modules([str(ORDNER)]) if not m.name.startswith("_")}
    bekannt = detektoren._BEKANNTE_MODULE
    assert len(set(bekannt)) == len(bekannt), f"doppelte Einträge in _BEKANNTE_MODULE: {bekannt}"
    assert set(bekannt) == im_ordner, (
        "anonymisierer/detektoren/__init__.py: _BEKANNTE_MODULE muss ALLE Module des Pakets nennen (Rückfall für "
        f"die EXE) – fehlt: {sorted(im_ordner - set(bekannt))}, überzählig: {sorted(set(bekannt) - im_ordner)}")


def test_alle_module_der_liste_sind_geladen():
    for name in detektoren._BEKANNTE_MODULE:
        assert f"{detektoren.__name__}.{name}" in sys.modules, name
    assert detektoren.LADEFEHLER == []


def test_exe_ohne_modulliste_laedt_dasselbe_register():
    """Liefert pkgutil.iter_modules nichts (EXE), entstehen dieselben Detektoren in derselben Reihenfolge wie im
    Quelltext-Betrieb – kein Erkennungsmodul fällt still weg."""
    normal, exe = _laden("normal"), _laden("exe")
    assert normal["ladefehler"] == [] and exe["ladefehler"] == []
    erwartet = sorted(f"{detektoren.__name__}.{n}" for n in detektoren._BEKANNTE_MODULE)
    assert exe["module"] == normal["module"] == erwartet
    assert exe["register"] == normal["register"]
    # der frische Prozess sieht dasselbe Register wie dieser Testlauf (ohne Detektoren, die Tests selbst anmelden)
    hier = [e.name for e in detektoren.REGISTER if e.funktion.__module__.startswith("anonymisierer.")]
    assert [e[0] for e in normal["register"]] == hier


def test_fehlendes_modul_in_der_exe_wird_gemeldet():
    """Fehlt ein Modul der Liste zur Laufzeit (unvollständig gebaute EXE), landet das in LADEFEHLER – die Analyse
    meldet es dann als Warnung (ERKENNUNG_FEHLER) statt still weniger zu finden."""
    erg = _laden("exe_luecke")
    assert f"{detektoren.__name__}.struktur_formular" not in erg["module"]
    assert any("struktur_formular" in f for f in erg["ladefehler"]), erg["ladefehler"]
    assert len(erg["ladefehler"]) == 1, erg["ladefehler"]      # die übrigen Module laden trotzdem

"""Detektor "kundenliste" (Vertrag Abschnitt 6): Kunden der importierten Kundenliste im Dokument erkennen.

Die Kundenliste kommt über den Analyse-Kontext (analysiere_pdf(..., kundenliste=...)). Erkannt wird ein Kunde
über ein starkes Merkmal (voller Name, Kunden-/Vertragsnummer, IBAN, E-Mail); dann werden alle seine Merkmale
geschwärzt (Quelle "kundenliste", Sicherheit 1.0). Ohne Kundenliste liefert der Detektor nichts.
"""

from __future__ import annotations

from . import ALLE_PROFILE, detektor

KATEGORIEN = {"namen", "geburt", "strasse", "plzort", "iban", "vertrag", "email", "telefon", "kfz"}


@detektor("kundenliste", KATEGORIEN, ALLE_PROFILE)
def kundenliste(dok, kontext):
    """Merkmale bekannter Kunden (gesalzene Prüfwerte, kein Klartext)."""
    liste = getattr(kontext, "kundenliste", None)
    if liste is None or not callable(getattr(liste, "treffer", None)) or getattr(liste, "attrappe", False):
        return []
    return list(liste.treffer(dok) or [])

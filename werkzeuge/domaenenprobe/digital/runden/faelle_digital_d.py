# Domänen-Probe "Finanzen, Behörden, Digitales" – Runde 3: drei Gegenproben (Aufzählung, alte Kontoverbindung,
# verschleierte E-Mail). Alles erfunden; Steuer-IDs mit gültiger Prüfziffer.
def F(name, zeilen, geheim, scans=(), **kw):
    return dict(name=name, zeilen=zeilen, geheim=geheim, scans=scans, **kw)


FAELLE = [
    F("steuer_id_aufzaehlung", [
        "Antrag auf Elterngeld – Angaben zu den Eltern",
        "Steuer-ID beider Elternteile: 73 852 902 642 und 86 815 297 436",
        "IdNr.\t\t91 600 237 450\t\t17 490 854 263",
    ], ["73852902642", "86815297436", "91600237450", "17490854263"]),
    F("kontoverbindung_alt", [
        "Beitragseinzug (Altvertrag 1998)",
        "Kontoverbindung: 7362514098, BLZ 720 500 00",
        "Bankverbindung: Konto 2468013579 bei der Stadtsparkasse Augsburg (BLZ 720 500 00)",
    ], ["7362514098", "2468013579"]),
    F("email_verschleiert", [
        "Rückmeldung zur Schadenmeldung",
        "Bitte schreiben Sie mir an q.zwackelhuber(at)gmx.de oder quirin.zw [at] web [dot] de",
    ], ["q.zwackelhuber(at)gmx.de", "quirin.zw [at] web [dot] de"]),
]

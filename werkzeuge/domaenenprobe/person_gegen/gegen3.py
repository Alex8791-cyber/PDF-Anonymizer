# Gegenprüfung Sparte Person, Teil 3: Nachproben (Häufigkeit/Abgrenzung, Gefahr der Abhilfe). Erfundene Daten.
def F(name, zeilen, geheim, scans=(), **kw):
    d = dict(name=name, zeilen=zeilen, geheim=geheim, scans=scans)
    d.update(kw)
    return d


FAELLE = [
    # B8: übliches Briefbild (Absenderzeile über dem Anschriftfeld) und Etikett nur mit Namen
    F("b8_din5008", [
        "PVS Südbayern GmbH - Postfach 20 11 33 - 80011 München",
        "Frau",
        "Ilse Wohlgemuth-Brandl",
        "Am Mühlbach 12",
        "83646 Bad Tölz",
        "Rechnungsnummer: 2024-118733",
    ], ["Wohlgemuth", "Am Mühlbach 12", "83646"]),
    F("b8_firmazeile_block", [
        "Privatärztliche Verrechnungsstelle Südbayern GmbH",
        "Frau Ilse Wohlgemuth-Brandl",
        "Am Mühlbach 12",
        "83646 Bad Tölz",
    ], ["Wohlgemuth", "Am Mühlbach 12", "83646"]),
    F("b8_name_dann_anschrift", [
        "Klinikum Rosenheim GmbH",
        "Rechnungsempfänger: Anton Seidl",
        "Fichtenstr. 9, 94036 Passau",
    ], ["Seidl", "Fichtenstr. 9", "94036"]),

    # B16: übrige Zeilen des Prüferfalls und Nachbarn
    F("b16_familie", [
        "Familienanamnese: Mutter Morbus Parkinson; Vater Alzheimer-Demenz",
        "Behandlung: Baker-Zyste rechts, Dupuytren-Kontraktur links, Morbus Scheuermann",
    ], []),
    F("b16_familie_var", [
        "Familienanamnese: Vater Morbus Alzheimer seit 2020",
    ], []),
    F("b16_adjektive", [
        "Diagnosen: Distale Radiusfraktur rechts (S52.51)",
        "Chronische Lumbalgie seit 2019",
        "Arterielle Hypertonie, medikamentös eingestellt",
    ], []),
    F("b16_adjektive_var", [
        "Diagnosen: Proximale Humerusfraktur links (S42.21)",
        "Essentielle Hypertonie, eingestellt",
        "Rezidivierende Lumboischialgie",
    ], []),

    # B1: Bestandsliste mit Punkt-Kennungen (Spaltenkopf) neben Beträgen
    F("b1_bestandsliste", [
        "Vertragsübersicht",
        "Vertragsnr.\t\tSparte\t\tBeitrag",
        "12.345.678\t\tKV\t\t612,48 €",
        "23.456.789\t\tPV\t\t48,20 €",
    ], ["12345678", "23456789"]),

    # B2/B4: Geburtsdatum mit "geboren" hinter dem Datum
    F("b2_geboren_dahinter", [
        "Kindernachversicherung",
        "Unsere Tochter Frieda wurde am 14.09.2026 geboren.",
    ], ["14.09.2026"]),
    F("b4_kontrolle_etikett", [
        "Kindernachversicherung",
        "Tag der Geburt: 02.10.2026",
    ], ["02.10.2026"]),

    # Gefahr einer Abhilfe für B2: Arztname + jüngeres Behandlungsdatum (darf nicht Geburtsdatum werden)
    F("b2_kontrolle_behandlung_neu", [
        "Angaben zu Arztbesuchen",
        "Dr. Jens Abendroth, 14.05.2024: Kontrolle ohne Befund",
    ], ["Abendroth"]),
]

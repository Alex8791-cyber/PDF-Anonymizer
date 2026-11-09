"""Dateiverwaltung: PDFs aus Dateien und Ordnern einsammeln."""

from pathlib import Path

def sammle_pdfs(pfade: list[str]) -> list[Path]:
    """Nimmt Dateien UND Ordner entgegen, liefert alle PDFs darin."""
    gefunden: list[Path] = []
    for p in pfade:
        pfad = Path(p)
        if pfad.is_dir():
            for pdf in sorted(pfad.rglob("*.pdf")):
                if "anonymisiert" not in pdf.parts and not pdf.stem.endswith("_anonym"):
                    gefunden.append(pdf)
        elif pfad.suffix.lower() == ".pdf" and pfad.exists():
            gefunden.append(pfad)
    return list(dict.fromkeys(gefunden))

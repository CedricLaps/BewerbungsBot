# Dokumente

Hier liegen die Bewerbungsunterlagen, die der Bot verwendet:

- `CV.pdf` — der Lebenslauf, der bei jeder Bewerbung hochgeladen wird
  (Pfad konfigurierbar über `cv_path` in `config.json`).
- `certificates/` — Zeugnisse und Zertifikate
  (Pfad konfigurierbar über `certificates_path`).
- `anschreiben/` — eigene Beispiel-Anschreiben (.txt/.md/.pdf) als Stilvorlagen
  für die KI-Generierung (Pfad konfigurierbar über `cover_letter_samples_path`).

**Wichtig:** Ohne `CV.pdf` bricht jeder Bewerbungsversuch mit einer klaren
Fehlermeldung ab — der Bot sendet niemals Bewerbungen ohne Lebenslauf.

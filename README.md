# BewerbungsBot

Vollständig lokales Bewerbungsautomatisierungssystem für Softwareentwickler-Stellen:
Jobs sammeln → mit Keywords + lokalem LLM bewerten → Anschreiben generieren →
automatisch bewerben → alles im Dashboard verfolgen.

**Kein Cloud-LLM, keine API-Kosten** — die KI läuft komplett lokal über
[Ollama](https://ollama.com) (Standardmodell: `deepseek-r1`; unterstützt außerdem
`qwen2.5`, `llama3.1`, `mistral`).

## Architektur

```
scrapers/   LinkedIn, StepStone, Indeed, Greenhouse, Lever, Personio,
            Workday, Firmenkarriereseiten
backend/    Konfiguration, LLM-Client (Ollama), Matching, Pipeline, Scheduler
apply/      Automatische Bewerbung per Playwright (Greenhouse, Lever,
            Personio, Workday)
database/   SQLite via SQLAlchemy (Duplikatsvermeidung, Status-Tracking)
dashboard/  FastAPI-Weboberfläche mit Filtern und Statistiken
documents/  CV.pdf und Zeugnisse
logs/       App-Log, Fehler-Log, Screenshots jedes Bewerbungsversuchs
tests/      Unit-Tests (pytest)
```

## Schnellstart mit Docker (ein Befehl)

```bash
docker compose up -d
```

Das startet drei Container:

1. **ollama** — lokaler LLM-Server (Port 11434)
2. **ollama-init** — lädt einmalig das Modell `deepseek-r1` herunter
3. **bot** — Scheduler + Dashboard auf <http://localhost:8000>

Vorher:

1. `documents/CV.pdf` ablegen.
2. In `config.json` `email`, `phone` und `linkedin` eintragen.

## Lokale Installation (ohne Docker)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
playwright install chromium

# Ollama installieren (https://ollama.com) und Modell laden:
ollama pull deepseek-r1

# Dashboard + Scheduler starten:
python main.py serve
```

## CLI-Befehle

| Befehl | Wirkung |
|---|---|
| `python main.py serve` | Dashboard + Scheduler starten (Standard) |
| `python main.py scrape` | Einmalig Jobs sammeln und bewerten |
| `python main.py apply --limit 5` | Einmalig bis zu 5 Bewerbungen versenden |
| `python main.py score` | Unbewertete Jobs nachbewerten |
| `python main.py stats` | Statistiken als JSON ausgeben |
| `python main.py workday-login <URL>` | Workday-Sitzung interaktiv speichern |

## Konfiguration (`config.json`)

Die wichtigsten Schlüssel — Vorlage: `config.example.json`:

| Schlüssel | Bedeutung |
|---|---|
| `ollama_model` | `deepseek-r1` (Standard), `qwen2.5`, `llama3.1`, `mistral` |
| `ollama_url` | Ollama-Endpunkt; in Docker automatisch `http://ollama:11434/api/generate` |
| `min_match_score` | Nur Jobs ab diesem Score (0–100) werden beworben, Standard 60 |
| `auto_submit` | `false` = Formulare nur ausfüllen, nicht absenden (Testmodus) |
| `headless` | `false` = Browser sichtbar laufen lassen (Debugging) |
| `max_applications_per_run` | Obergrenze pro Bewerbungslauf |
| `greenhouse_boards` | Board-Tokens, z.B. `["gitlab", "n26"]` → `boards-api.greenhouse.io/v1/boards/<token>/jobs` |
| `lever_companies` | Account-Namen, z.B. `["backmarket"]` → `api.lever.co/v0/postings/<name>` |
| `personio_companies` | Subdomains, z.B. `["firma"]` → `firma.jobs.personio.de/xml` |
| `workday_sites` | Liste von `{"host": "firma.wd3.myworkdayjobs.com", "site": "External", "company": "Firma"}` |
| `company_pages` | URLs von Firmenkarriereseiten, die nach passenden Stellenlinks durchsucht werden |

ENV-Variablen überschreiben die Datei: `OLLAMA_URL`, `OLLAMA_MODEL`,
`DATABASE_PATH`, `LOGS_DIR`, `HEADLESS`, `AUTO_SUBMIT`, `SCHEDULER_ENABLED`,
`DASHBOARD_HOST`, `DASHBOARD_PORT`, `CONFIG_PATH`.

## Ablauf der Pipeline

1. **Sammeln** (alle 6 h): Alle aktivierten Scraper laufen; Ergebnisse werden
   dedupliziert (URL + Firma/Titel/Ort) und in SQLite gespeichert.
2. **Bewerten**: Keyword-Score (positive/negative Keywords) + LLM-Score von
   Ollama, kombiniert 50/50. Ab `min_match_score` → Status *Passend*, sonst
   *Aussortiert*. Ist Ollama offline, zählt nur der Keyword-Score.
3. **Bewerben** (alle 12 h): Für jede passende Stelle generiert das LLM ein
   individuelles Anschreiben (max. 250 Wörter, Sprache automatisch erkannt),
   Playwright füllt das Formular aus, lädt den Lebenslauf hoch und sendet ab.
   Jeder Versuch wird mit Screenshot protokolliert.

## Plattform-Hinweise

- **Greenhouse / Lever / Personio**: vollautomatisch (Formular erkennen,
  ausfüllen, CV-Upload, Anschreiben, absenden).
- **Workday**: verlangt ein Bewerberkonto. Einmalig
  `python main.py workday-login <URL>` ausführen und anmelden — die Sitzung
  wird gespeichert und für künftige Bewerbungen wiederverwendet. Ohne Sitzung
  wird der Job mit klarer Fehlermeldung zur manuellen Bearbeitung markiert.
- **LinkedIn / StepStone / Indeed** dienen als *Quellen* für die Jobsuche.
  Stellen, die auf ein unterstütztes ATS verlinken, werden automatisch
  beworben; alle anderen erscheinen im Dashboard zur manuellen Bewerbung.
- Indeed setzt Cloudflare-Bot-Schutz ein, LinkedIn drosselt (HTTP 429) —
  beides wird erkannt und sauber abgebrochen statt zu crashen.

## Verantwortungsvoller Betrieb

- Die Scraper halten konfigurierbare Pausen ein (`request_delay_seconds`) und
  begrenzen die Seitenzahl (`max_pages_per_search`). Automatisiertes Auslesen
  kann gegen die Nutzungsbedingungen einzelner Portale verstoßen — die
  Verantwortung für den Einsatz liegt beim Betreiber.
- Empfehlung: zunächst mit `"auto_submit": false` testen und die ausgefüllten
  Formulare anhand der Screenshots in `logs/screenshots/` prüfen, bevor
  automatisch abgesendet wird.
- Jedes generierte Anschreiben wird in der Datenbank gespeichert und ist im
  Dashboard einsehbar.

## Tests

```bash
pytest
```

Getestet werden Matching, Spracherkennung, LLM-Client (gemockt), Repository
inkl. Duplikatsvermeidung sowie die API-Scraper (gemockt).

## Logs

- `logs/app.log` — alle Ereignisse (rotierend)
- `logs/errors.log` — nur Fehler (HTTP-Fehler, Formularfehler, …)
- `logs/screenshots/` — Screenshot jedes Bewerbungsversuchs
  (`<jobid>_<firma>_<submitted|error|filled>_<zeitstempel>.png`)

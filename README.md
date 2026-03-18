# GATE Portal Automation

Automates login to the GATE portal, solves arithmetic captcha (OCR with manual fallback), and writes extracted result data per candidate.

## Architecture

- **Facade**: `GateResultService` orchestrates the complete workflow.
- **Strategy**: `CaptchaSolver` implementations (`manual`, `ocr`, `hybrid`).
- **Factory**: `CaptchaSolverFactory` creates strategy instances.
- **Observer**: Multiple result sinks (`ConsoleResultSink`, `CsvResultSink`) subscribe to each result.
- **SOLID**:
  - SRP: Each class has one responsibility.
  - OCP/LSP: New solver/client implementations plug in via interfaces.
  - ISP/DIP: Service depends on abstractions in `core/interfaces.py`.

## Project layout

- `gate_automation/core/` — interfaces, models, orchestrator service
- `gate_automation/infrastructure/` — CSV loader, captcha solvers, Playwright client, sinks
- `data/credentials.csv` — input credentials
- `output/results.csv` — output data

## Prerequisites

- Python 3.10+
- Tesseract OCR binary installed on OS (required for OCR mode)
- Browser binaries for Playwright

## Setup

```bash
cd /home/barath/Documents/Gate-Res
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Credential CSV format

`data/credentials.csv`

```csv
enrollment_id,password
G229J81,Manish@04
```

## Run

Hybrid mode (OCR first, then manual input fallback):

```bash
python -m gate_automation.main --captcha-mode hybrid --headful
```

Manual mode:

```bash
python -m gate_automation.main --captcha-mode manual --headful
```

Output is appended to `output/results.csv`.

## Test

```bash
pytest -q
```

## Notes

- Captcha OCR is best-effort; if OCR fails, hybrid mode asks manual answer.
- Portal HTML can change; selectors in `playwright_client.py` may need occasional tuning.

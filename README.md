# Caney Flows

This repository scrapes the Cumberland River Basin generation schedule page and stores normalized dam generation data for:

- Wolf Creek
- Dale Hollow
- Cordell Hull
- Center Hill
- Old Hickory
- J Percy Priest
- Cheatham
- Barkley

## Unit Classification Rules

- Wolf Creek: 40-50 MW = 1 unit, above 50 MW = 2+ units
- Center Hill: 45-55 MW = 1 unit, above 55 MW = 2+ units
- Dale Hollow: 14-18 MW = 1 unit, above 18 MW = 2+ units

For dams without provided thresholds (Cordell Hull, Old Hickory, J Percy Priest, Cheatham, Barkley), `units` is set to `unknown`.

## Local Run

```bash
pip install -r requirements.txt
python scripts/scrape_generation.py
```

Output is written to `data/generation_schedule.json`.

## GitHub Action

The workflow is in `.github/workflows/scrape-generation.yml`.

- Runs every 30 minutes
- Can also be triggered manually with `workflow_dispatch`
- Commits `data/generation_schedule.json` back to the repo when changes are detected

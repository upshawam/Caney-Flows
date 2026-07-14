import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

URL = "https://www.lrn-wc.usace.army.mil/preschedule.shtml"
OUTPUT_PATH = Path(os.getenv("OUTPUT_PATH", "data/generation_schedule.json"))

DAMS = [
    "Wolf Creek",
    "Dale Hollow",
    "Cordell Hull",
    "Center Hill",
    "Old Hickory",
    "J Percy Priest",
    "Cheatham",
    "Barkley",
]

DAM_HEADER_ALIASES = {
    "Wolf Creek": ["wolf creek"],
    "Dale Hollow": ["dale hollow"],
    "Cordell Hull": ["cordell hull"],
    "Center Hill": ["center hill"],
    "Old Hickory": ["old hickory"],
    "J Percy Priest": ["j percy priest", "j. percy priest"],
    "Cheatham": ["cheatham"],
    "Barkley": ["barkley"],
}

UNIT_RULES = {
    "Wolf Creek": (40, 50),
    "Center Hill": (45, 55),
    "Dale Hollow": (14, 18),
}


def classify_units(dam_name: str, mw_value: float) -> str:
    if dam_name not in UNIT_RULES:
        return "unknown"

    min_one_unit, max_one_unit = UNIT_RULES[dam_name]

    if mw_value <= 0:
        return "0"
    if min_one_unit <= mw_value <= max_one_unit:
        return "1"
    if mw_value > max_one_unit:
        return "2+"
    return "unknown"


def parse_mw(cell_text: str):
    value = cell_text.strip().replace(",", "")
    if value in {"", "---", "--", "N/A"}:
        return None

    match = re.search(r"-?\d+(?:\.\d+)?", value)
    if not match:
        return None

    number = float(match.group(0))
    if number.is_integer():
        return int(number)
    return number


def find_schedule_table(soup: BeautifulSoup):
    required = ["wolf creek", "dale hollow", "cordell hull", "center hill"]

    for table in soup.find_all("table"):
        table_text = " ".join(table.stripped_strings).lower()
        if all(name in table_text for name in required):
            return table

    raise RuntimeError("Could not find schedule table with all target dams.")


def build_rows(table):
    rows = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        rows.append([c.get_text(" ", strip=True) for c in cells])
    return rows


def detect_column_indexes(rows):
    # Use the first several header-like rows to map dam names to column indexes.
    header_rows = rows[:6]
    indexes = {}

    for dam_name in DAMS:
        aliases = DAM_HEADER_ALIASES[dam_name]
        for row in header_rows:
            for idx, text in enumerate(row):
                lowered_text = text.lower()
                if any(alias in lowered_text for alias in aliases):
                    indexes[dam_name] = idx
                    break
            if dam_name in indexes:
                break

    missing = [d for d in DAMS if d not in indexes]
    if missing:
        raise RuntimeError(f"Missing dam column indexes for: {', '.join(missing)}")

    return indexes


def normalize_time(value: str):
    raw = value.strip()
    if raw.upper() == "TOTALS":
        return None

    digits = re.sub(r"\D", "", raw)
    if len(digits) == 3:
        digits = f"0{digits}"

    if len(digits) == 4:
        return digits
    return None


def parse_schedule(rows, column_indexes):
    schedules = {dam: [] for dam in DAMS}

    for row in rows:
        if not row:
            continue

        time_value = normalize_time(row[0])
        if not time_value:
            continue

        for dam_name, col_idx in column_indexes.items():
            if col_idx >= len(row):
                continue

            mw = parse_mw(row[col_idx])
            units = classify_units(dam_name, mw) if mw is not None else "unknown"

            schedules[dam_name].append(
                {
                    "time": time_value,
                    "mw": mw,
                    "units": units,
                }
            )

    return schedules


def fetch_html():
    source_html_path = os.getenv("SOURCE_HTML_PATH")
    if source_html_path:
        path = Path(source_html_path)
        if not path.exists():
            raise RuntimeError(f"SOURCE_HTML_PATH does not exist: {path}")
        return path.read_text(encoding="utf-8"), f"file://{path}"

    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )

    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        )
    }

    urls = [URL, URL.replace("https://", "http://")]
    last_error = None

    for candidate in urls:
        try:
            response = session.get(candidate, timeout=30, headers=headers)
            response.raise_for_status()
            return response.text, candidate
        except requests.RequestException as exc:
            last_error = exc

    raise RuntimeError(f"Unable to fetch schedule page: {last_error}")


def run():
    html, source_url = fetch_html()

    soup = BeautifulSoup(html, "html.parser")
    table = find_schedule_table(soup)
    rows = build_rows(table)
    column_indexes = detect_column_indexes(rows)
    schedules = parse_schedule(rows, column_indexes)

    payload = {
        "source_url": source_url,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "classification_rules": {
            "Wolf Creek": "40-50 MW = 1 unit; >50 MW = 2+ units",
            "Center Hill": "45-55 MW = 1 unit; >55 MW = 2+ units",
            "Dale Hollow": "14-18 MW = 1 unit; >18 MW = 2+ units",
        },
        "all_dams": DAMS,
        "dam_column_indexes": column_indexes,
        "schedules": schedules,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    run()

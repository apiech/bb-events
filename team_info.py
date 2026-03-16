import argparse
import os
import re
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

from bb_xml_client import get_client


def _load_env(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k and v and k not in os.environ:
                os.environ[k] = v


def _login(session: requests.Session) -> None:
    _load_env()
    get_client()


def get_teaminfo(session: requests.Session, team_id: int) -> dict:
    info = get_client().get_teaminfo(team_id)
    return {
        "team_id": team_id,
        "team_name": info.team_name or "",
        "short_name": info.short_name or "",
        "league_id": info.league.id if info.league is not None else None,
        "league_name": info.league.name if info.league is not None else None,
        "country_id": info.country.id if info.country is not None else None,
        "country_name": info.country.name if info.country is not None else None,
        "is_bot": info.is_bot,
    }


def get_team_history_from_webpage(session: requests.Session, team_id: int) -> list[dict]:
    url = f"https://buzzerbeater.com/team/{team_id}/history.aspx"
    resp = session.get(url)
    resp.raise_for_status()

    season_any_pattern = re.compile(
        r"In season (\d+),\s*(.+?)\s+(?:were|was|made|won|lost|played|finished|qualified).*",
        re.IGNORECASE,
    )

    soup = BeautifulSoup(resp.text, "html.parser")
    spans = soup.find_all("span")

    history_entries = []
    for span in spans:
        text = span.get_text(" ", strip=True)
        if "In season" not in text:
            continue
        match = season_any_pattern.search(text)
        if not match:
            continue
        season = int(match.group(1))
        team_name = match.group(2).strip()
        style = span.get("style") or ""
        is_muted = "color: gray" in style.lower()
        history_entries.append(
            {
                "season": season,
                "team_name": team_name,
                "league_name": None,
                "is_muted": is_muted,
            }
        )

    history_entries.sort(key=lambda x: x["season"], reverse=True)
    return history_entries


def first_season(history_entries: list[dict], current_team_name: str | None = None) -> int | None:
    if not history_entries:
        return None
    non_muted = [e for e in history_entries if not e.get("is_muted")]
    if non_muted:
        return min(entry["season"] for entry in non_muted)
    if current_team_name:
        current_name_entries = [
            entry for entry in history_entries if entry.get("team_name") == current_team_name
        ]
        if current_name_entries:
            return min(entry["season"] for entry in current_name_entries)
    return min(entry["season"] for entry in history_entries)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--teamid", type=int, required=True)
    args = parser.parse_args()

    _load_env()
    session = requests.Session()
    _login(session)

    info = get_teaminfo(session, args.teamid)
    history = get_team_history_from_webpage(session, args.teamid)
    first = first_season(history, info["team_name"])

    print(f"team_id: {info['team_id']}")
    print(f"team_name: {info['team_name']}")
    print(f"short_name: {info['short_name']}")
    print(f"is_bot: {info['is_bot']}")
    if first is not None:
        print(f"first_season: {first}")
    else:
        print("first_season: unknown")


if __name__ == "__main__":
    main()

import argparse
import contextlib
import io
import math
import os
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import requests

from bb_xml_client import get_client
from comments import Comments
from event import ShotEvent, convert
from main import get_xml_text, parse_xml
from buzzerbeaters import FT_PER_PX


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


def _current_season(session: requests.Session) -> int:
    seasons = [
        (season.id, season.start or "", season.finish or "")
        for season in get_client().get_seasons().seasons
        if season.id is not None
    ]
    if not seasons:
        raise RuntimeError("No seasons found")
    today = date.today()
    for sid, start, finish in seasons:
        try:
            s = date.fromisoformat(start)
            f = date.fromisoformat(finish)
        except Exception:
            continue
        if s <= today <= f:
            return sid
    return max(sid for sid, _, _ in seasons)


def _all_seasons(session: requests.Session) -> list[int]:
    return sorted(
        season.id for season in get_client().get_seasons().seasons if season.id is not None
    )


def _schedule_matches(session: requests.Session, team_id: int, season: int):
    matches = []
    for match in get_client().get_schedule(team_id=team_id, season=season).matches:
        if match.id is None or match.start is None:
            continue
        if match.home_team.score is None or match.away_team.score is None:
            continue
        matches.append((match.id, match.start))
    return matches


def _sort_key(start: str):
    try:
        return datetime.fromisoformat(start.replace("Z", "+00:00"))
    except Exception:
        return start


def _collect_distances(match_ids: list[int]):
    three_dists = []
    two_dists = []
    for matchid in match_ids:
        text = get_xml_text(matchid)
        with contextlib.redirect_stdout(io.StringIO()):
            events, ht, at = parse_xml(text)
            comments = Comments()
            for ev in events:
                ev.comment = comments.get_comment(ev, [ht, at])
            baseevents = convert(events)

        for be in baseevents:
            if not isinstance(be, ShotEvent) or be.shot_pos is None:
                continue
            basket_x, basket_y = (347, 96) if be.att_team == 0 else (21, 96)
            dx = be.shot_pos.x - basket_x
            dy = be.shot_pos.y - basket_y
            dist_ft = math.sqrt(dx * dx + dy * dy) * FT_PER_PX
            if be.is_3pt():
                three_dists.append(dist_ft)
            else:
                two_dists.append(dist_ft)
    return three_dists, two_dists


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--teamid", type=int, required=True)
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--count", type=int, default=10, help="Number of most recent games")
    parser.add_argument("--bin-width", type=float, default=0.25)
    parser.add_argument("--out", default="output/charts/team_shot_distance_hist.png")
    args = parser.parse_args()

    _load_env()
    session = requests.Session()
    _login(session)

    current = _current_season(session)
    seasons = _all_seasons(session)
    seasons = [s for s in seasons if s <= current]
    seasons.sort(reverse=True)

    match_ids = []
    if args.season is not None:
        seasons = [args.season]

    for season in seasons:
        matches = _schedule_matches(session, args.teamid, season)
        matches.sort(key=lambda m: _sort_key(m[1]), reverse=True)
        for mid, _ in matches:
            match_ids.append(mid)
            if len(match_ids) >= args.count:
                break
        if len(match_ids) >= args.count:
            break

    three_dists, two_dists = _collect_distances(match_ids)

    bin_width = args.bin_width
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)

    # 3PT histogram
    if three_dists:
        bins = np.arange(min(three_dists), max(three_dists) + bin_width, bin_width)
    else:
        bins = 10
    axes[0].hist(three_dists, bins=bins, color="#4C78A8", alpha=0.8)
    axes[0].axvline(23.75, color="#F58518", linestyle="--", label="Arc 23.75 ft")
    axes[0].axvline(22.0, color="#54A24B", linestyle=":", label="Corner 22 ft")
    axes[0].set_title("3PT Distance (ft)")
    axes[0].set_xlabel("Feet")
    axes[0].set_ylabel("Count")
    axes[0].legend()

    # 2PT histogram
    if two_dists:
        bins = np.arange(min(two_dists), max(two_dists) + bin_width, bin_width)
    else:
        bins = 10
    axes[1].hist(two_dists, bins=bins, color="#72B7B2", alpha=0.8)
    axes[1].axvline(23.75, color="#F58518", linestyle="--", label="Arc 23.75 ft")
    axes[1].axvline(22.0, color="#54A24B", linestyle=":", label="Corner 22 ft")
    axes[1].set_title("2PT Distance (ft)")
    axes[1].set_xlabel("Feet")
    axes[1].legend()

    plt.tight_layout()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=150)
    print(out_path)


if __name__ == "__main__":
    main()

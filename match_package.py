from __future__ import annotations

import argparse
import hashlib
import json
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from game import Game
from main import parse_xml


SCHEMA_VERSION = "MatchPackageV1"
DEFAULT_PARSER_VERSION = "bb-events-match-package-v1"


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_play_by_play_export(match_id: int, report_text: str) -> dict[str, Any]:
    events, home_team, away_team = parse_xml(report_text)
    args = Namespace(
        print_events=False,
        print_stats=False,
        save_charts=False,
        verify=False,
        username=None,
        password=None,
    )
    game = Game(str(match_id), events, home_team, away_team, args, [])
    game.play()
    return game.to_dict()


def compute_content_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def build_match_package(
    match_id: int,
    *,
    season: int | None,
    boxscore: dict[str, Any],
    play_by_play: dict[str, Any],
    parser_version: str = DEFAULT_PARSER_VERSION,
    raw_boxscore_key: str | None = None,
    raw_report_key: str | None = None,
) -> dict[str, Any]:
    match_summary = build_match_summary(
        match_id=match_id,
        season=season,
        boxscore=boxscore,
        play_by_play=play_by_play,
    )

    base_package = {
        "schemaVersion": SCHEMA_VERSION,
        "matchId": str(match_id),
        "parserVersion": parser_version,
        "sourceArtifacts": {
            "boxscoreKey": raw_boxscore_key,
            "reportKey": raw_report_key,
        },
        "match": match_summary,
        "boxscore": boxscore,
        "playByPlay": play_by_play,
        "ingestMetadata": {
            "season": season,
        },
    }

    package = json.loads(json.dumps(base_package))
    package["ingestMetadata"]["generatedAt"] = datetime.now(timezone.utc).isoformat()
    package["contentHash"] = compute_content_hash(base_package)
    return package


def build_match_summary(
    *,
    match_id: int,
    season: int | None,
    boxscore: dict[str, Any],
    play_by_play: dict[str, Any],
) -> dict[str, Any]:
    home_team = boxscore.get("homeTeam") or {}
    away_team = boxscore.get("awayTeam") or {}
    home_export = play_by_play.get("teamHome") or {}
    away_export = play_by_play.get("teamAway") or {}
    events = play_by_play.get("events") or []

    return {
        "matchId": str(match_id),
        "season": season,
        "type": boxscore.get("type"),
        "startTime": boxscore.get("startTime"),
        "endTime": boxscore.get("endTime"),
        "neutral": boxscore.get("neutral"),
        "eventCount": len(events),
        "homeTeam": {
            "id": _string_or_none(home_team.get("id") or home_export.get("id")),
            "teamName": home_team.get("teamName") or home_export.get("name"),
            "score": home_team.get("score")
            or _nested_points(home_export),
        },
        "awayTeam": {
            "id": _string_or_none(away_team.get("id") or away_export.get("id")),
            "teamName": away_team.get("teamName") or away_export.get("name"),
            "score": away_team.get("score")
            or _nested_points(away_export),
        },
    }


def save_match_package(package: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(package, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _nested_points(team: dict[str, Any]) -> int | None:
    stats = team.get("stats") or {}
    total = stats.get("total") or {}
    points = total.get("pts")
    if points is None:
        return None
    return int(points)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a MatchPackageV1 from normalized boxscore and bb-events play-by-play data.",
    )
    parser.add_argument("--matchid", required=True, type=int, help="Numeric match id")
    parser.add_argument("--season", type=int, default=None, help="Resolved season for the match")
    parser.add_argument(
        "--boxscore-json",
        required=True,
        help="Path to normalized boxscore JSON",
    )
    parser.add_argument(
        "--play-by-play-json",
        default=None,
        help="Path to a prebuilt bb-events normalized play-by-play export",
    )
    parser.add_argument(
        "--report-input",
        default=None,
        help="Path to the raw match report XML/HTML page used by bb-events",
    )
    parser.add_argument(
        "--parser-version",
        default=DEFAULT_PARSER_VERSION,
        help="Parser version tag embedded in the package",
    )
    parser.add_argument("--raw-boxscore-key", default=None, help="S3 or storage key for the raw boxscore artifact")
    parser.add_argument("--raw-report-key", default=None, help="S3 or storage key for the raw report artifact")
    parser.add_argument(
        "--out",
        default=None,
        help="Destination JSON path (default: output/match-packages/<matchid>.json)",
    )
    args = parser.parse_args()

    if not args.play_by_play_json and not args.report_input:
        raise SystemExit("Either --play-by-play-json or --report-input is required.")

    boxscore = load_json(args.boxscore_json)
    if args.play_by_play_json:
        play_by_play = load_json(args.play_by_play_json)
    else:
        report_text = Path(args.report_input).read_text(encoding="utf-8")
        play_by_play = build_play_by_play_export(args.matchid, report_text)

    package = build_match_package(
        args.matchid,
        season=args.season,
        boxscore=boxscore,
        play_by_play=play_by_play,
        parser_version=args.parser_version,
        raw_boxscore_key=args.raw_boxscore_key,
        raw_report_key=args.raw_report_key,
    )

    out_path = (
        Path(args.out)
        if args.out
        else Path("output") / "match-packages" / f"{args.matchid}.json"
    )
    save_match_package(package, out_path)


if __name__ == "__main__":
    main()

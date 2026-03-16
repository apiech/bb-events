import argparse
import os
import sqlite3
import sys
from datetime import date
from pathlib import Path

import requests

from bb_xml_client import get_client
from first_active_match import _schedule_matches, _parse_team_name, _sort_key, _login, _load_env
from main import get_xml_text
from match_package import build_play_by_play_export
from moments import extract_team_perspective_moments
from team_info import get_team_history_from_webpage, get_teaminfo, first_season

try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
except Exception:
    Console = None
    Progress = None


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


def _completed_matches(session: requests.Session, team_id: int, season: int):
    completed = []
    match_types = {}
    match_scores = {}
    match_seasons = {}
    for match in get_client().get_schedule(team_id=team_id, season=season).matches:
        if match.id is not None and match.home_team.score is not None and match.away_team.score is not None:
            completed.append(match.id)
            match_types[match.id] = match.type
            match_scores[match.id] = (match.home_team.score, match.away_team.score)
    return completed, match_types, match_scores, match_seasons


def _save_hits(db_path: str, rows) -> int:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    _ensure_columns(cur)
    inserted = 0
    for row in rows:
        cur.execute(
            """
            INSERT INTO buzzerbeaters (
                record_id, moment_id,
                match_id, team_id, team_name, opponent_id, opponent_name,
                perspective, scoring_team_id, scoring_team_name,
                player_id, player_name, period, game_clock, comment, match_type, is_home,
                event_kind, shot_type, shot_type_label, shot_result, free_throw_type, shot_x, shot_y, shot_distance, shot_distance_ft,
                score_before_home, score_before_away, score_after_home, score_after_away,
                team_score_before, opponent_score_before, team_score_after, opponent_score_after,
                final_team_score, final_opponent_score, outcome_changed,
                final_score_home, final_score_away, season
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(record_id) DO UPDATE SET
                moment_id=excluded.moment_id,
                team_name=excluded.team_name,
                opponent_id=excluded.opponent_id,
                opponent_name=excluded.opponent_name,
                perspective=excluded.perspective,
                scoring_team_id=excluded.scoring_team_id,
                scoring_team_name=excluded.scoring_team_name,
                player_name=excluded.player_name,
                comment=excluded.comment,
                match_type=excluded.match_type,
                is_home=excluded.is_home,
                event_kind=excluded.event_kind,
                shot_type=excluded.shot_type,
                shot_type_label=excluded.shot_type_label,
                shot_result=excluded.shot_result,
                free_throw_type=excluded.free_throw_type,
                shot_x=excluded.shot_x,
                shot_y=excluded.shot_y,
                shot_distance=excluded.shot_distance,
                shot_distance_ft=excluded.shot_distance_ft,
                score_before_home=excluded.score_before_home,
                score_before_away=excluded.score_before_away,
                score_after_home=excluded.score_after_home,
                score_after_away=excluded.score_after_away,
                team_score_before=excluded.team_score_before,
                opponent_score_before=excluded.opponent_score_before,
                team_score_after=excluded.team_score_after,
                opponent_score_after=excluded.opponent_score_after,
                final_team_score=excluded.final_team_score,
                final_opponent_score=excluded.final_opponent_score,
                outcome_changed=excluded.outcome_changed,
                final_score_home=excluded.final_score_home,
                final_score_away=excluded.final_score_away,
                season=excluded.season
            """,
            (
                row.get("record_id"),
                row.get("moment_id"),
                row.get("match_id"),
                row.get("team_id"),
                row.get("team_name"),
                row.get("opponent_id"),
                row.get("opponent_name"),
                row.get("perspective"),
                row.get("scoring_team_id"),
                row.get("scoring_team_name"),
                row.get("player_id"),
                row.get("player_name"),
                row.get("period"),
                row.get("gameclock"),
                row.get("comment"),
                row.get("match_type"),
                1 if row.get("is_home") else 0,
                row.get("event_kind"),
                row.get("shot_type"),
                row.get("shot_type_label"),
                row.get("shot_result"),
                row.get("free_throw_type"),
                row.get("shot_x"),
                row.get("shot_y"),
                None,
                row.get("shot_distance_ft"),
                row.get("score_before_home"),
                row.get("score_before_away"),
                row.get("score_after_home"),
                row.get("score_after_away"),
                row.get("team_score_before"),
                row.get("opponent_score_before"),
                row.get("team_score_after"),
                row.get("opponent_score_after"),
                row.get("final_team_score"),
                row.get("final_opponent_score"),
                1 if row.get("outcome_changed") else 0,
                row.get("final_score_home"),
                row.get("final_score_away"),
                row.get("season"),
            ),
        )
        if cur.rowcount:
            inserted += 1
    conn.commit()
    conn.close()
    return inserted


def _ensure_columns(cur: sqlite3.Cursor) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS buzzerbeaters (
            record_id TEXT,
            moment_id TEXT,
            match_id INTEGER,
            team_id INTEGER,
            team_name TEXT,
            opponent_id INTEGER,
            opponent_name TEXT,
            perspective TEXT,
            scoring_team_id INTEGER,
            scoring_team_name TEXT,
            player_id INTEGER,
            player_name TEXT,
            period TEXT,
            game_clock INTEGER,
            comment TEXT,
            match_type TEXT,
            is_home INTEGER,
            event_kind TEXT,
            shot_type TEXT,
            shot_type_label TEXT,
            shot_result TEXT,
            free_throw_type TEXT,
            shot_x INTEGER,
            shot_y INTEGER,
            shot_distance REAL,
            shot_distance_ft REAL,
            score_before_home INTEGER,
            score_before_away INTEGER,
            score_after_home INTEGER,
            score_after_away INTEGER,
            team_score_before INTEGER,
            opponent_score_before INTEGER,
            team_score_after INTEGER,
            opponent_score_after INTEGER,
            final_team_score INTEGER,
            final_opponent_score INTEGER,
            outcome_changed INTEGER,
            final_score_home INTEGER,
            final_score_away INTEGER,
            season INTEGER
        )
        """
    )

    cur.execute("PRAGMA table_info(buzzerbeaters)")
    cols = {row[1] for row in cur.fetchall()}
    additions = {
        "record_id": "TEXT",
        "moment_id": "TEXT",
        "perspective": "TEXT",
        "scoring_team_id": "INTEGER",
        "scoring_team_name": "TEXT",
        "event_kind": "TEXT",
        "shot_type": "TEXT",
        "shot_type_label": "TEXT",
        "shot_result": "TEXT",
        "free_throw_type": "TEXT",
        "shot_x": "INTEGER",
        "shot_y": "INTEGER",
        "shot_distance": "REAL",
        "shot_distance_ft": "REAL",
        "score_before_home": "INTEGER",
        "score_before_away": "INTEGER",
        "score_after_home": "INTEGER",
        "score_after_away": "INTEGER",
        "team_score_before": "INTEGER",
        "opponent_score_before": "INTEGER",
        "team_score_after": "INTEGER",
        "opponent_score_after": "INTEGER",
        "final_team_score": "INTEGER",
        "final_opponent_score": "INTEGER",
        "outcome_changed": "INTEGER",
        "final_score_home": "INTEGER",
        "final_score_away": "INTEGER",
        "season": "INTEGER",
    }
    for name, coltype in additions.items():
        if name not in cols:
            cur.execute(f"ALTER TABLE buzzerbeaters ADD COLUMN {name} {coltype}")

    # Ensure conflict target used by ON CONFLICT(...) exists on legacy DBs.
    cur.execute("PRAGMA index_list(buzzerbeaters)")
    indexes = [row[1] for row in cur.fetchall() if row[2]]
    key_cols = ["record_id"]
    has_unique_key = False
    for index_name in indexes:
        cur.execute(f"PRAGMA index_info({index_name!r})")
        cols_for_index = [row[2] for row in cur.fetchall()]
        if cols_for_index == key_cols:
            has_unique_key = True
            break
    if not has_unique_key:
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_buzzerbeaters_conflict_key
            ON buzzerbeaters(record_id)
            """
        )

def _phase_message(console, message: str) -> None:
    if console is not None:
        console.print(f"[dim]{message}[/dim]")
    else:
        print(message, file=sys.stderr, flush=True)


def _warning_message(console, message: str) -> None:
    if console is not None:
        console.print(f"[bold yellow]Warning:[/bold yellow] {message}")
    else:
        print(f"Warning: {message}", file=sys.stderr, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--teamid", type=int, required=True)
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--seasons", type=str, default=None, help="Comma-separated list")
    parser.add_argument("--season-from", type=int, dest="season_from", default=None)
    parser.add_argument("--season-to", type=int, dest="season_to", default=None)
    parser.add_argument("--auto-first-season", action="store_true", help="Auto-detect first season for current team name")
    parser.add_argument("--from-first-active", action="store_true", help="Start from the first active match of the team")
    parser.add_argument("--db", default="data/buzzerbeaters.db")
    parser.add_argument(
        "--tui",
        dest="tui",
        action="store_true",
        default=True,
        help="Rich TUI progress (default)",
    )
    parser.add_argument(
        "--no-tui",
        dest="tui",
        action="store_false",
        help="Disable Rich TUI progress",
    )
    args = parser.parse_args()
    console = Console(stderr=True) if args.tui and Console is not None else None
    _phase_message(console, f"Starting team buzzerbeater scan for team {args.teamid}...")
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    _phase_message(console, "Loading environment and credentials...")
    _load_env()
    username = os.getenv("BB_USERNAME")
    security_code = os.getenv("BB_SECURITY_CODE")
    if not username or not security_code:
        raise SystemExit("Missing BB_USERNAME or BB_SECURITY_CODE in environment")

    _phase_message(console, "Authenticating with BB API...")
    session = requests.Session()
    _login(session)

    # Resolve seasons to scan
    seasons = []
    detected = None
    if args.auto_first_season:
        _phase_message(console, "Auto-detecting first season from team history...")
        info = get_teaminfo(session, args.teamid)
        history = get_team_history_from_webpage(session, args.teamid)
        detected = first_season(history, info["team_name"])

    if args.seasons:
        seasons = [int(s.strip()) for s in args.seasons.split(",") if s.strip()]
    elif args.season is not None:
        seasons = [args.season]
    elif args.season_from is not None or args.season_to is not None:
        if args.season_from is None and args.auto_first_season and detected is not None:
            args.season_from = detected
        if args.season_from is None or args.season_to is None:
            raise SystemExit("Provide both --season-from and --season-to")
        if args.season_from > args.season_to:
            raise SystemExit("--season-from must be <= --season-to")
        seasons = list(range(args.season_from, args.season_to + 1))
    else:
        current = _current_season(session)
        if args.auto_first_season and detected is not None:
            seasons = list(range(detected, current + 1))
        else:
            seasons = [current]
    _phase_message(console, f"Resolved seasons to scan: {','.join(str(s) for s in seasons)}")
    if any(1 <= s <= 14 for s in seasons):
        _warning_message(console, "Buzzerbeaters are currently not tracked in seasons 1-14.")

    total_hits = 0
    total_inserted = 0
    total_matches = 0
    start_from_match = None
    start_from_time = None
    first_season_schedule = {}

    if args.from_first_active:
        _phase_message(console, "Resolving first active match in the first scanned season...")
        # Derive first active match within the first season in list
        first_season_num = min(seasons)
        schedule = _schedule_matches(session, args.teamid, first_season_num)
        schedule.sort(key=lambda m: _sort_key(m[1]))
        first_season_schedule = {mid: start for mid, start in schedule}
        names_seen = []
        for mid, start in schedule:
            xml = get_xml_text(mid)
            name = _parse_team_name(xml, args.teamid)
            if name:
                names_seen.append((mid, start, name))
        if names_seen:
            last_name = names_seen[-1][2]
            first_match = next(m for m in names_seen if m[2] == last_name)
            start_from_match = first_match[0]
            start_from_time = first_match[1]
            _phase_message(console, "First active match resolved.")
        else:
            _phase_message(console, "Could not derive first active match; using full season scan.")

    skipped = 0
    progress = None
    if args.tui and Progress is not None:
        progress = Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
        )

    if progress:
        progress.__enter__()

    for season in seasons:
        completed, match_types, match_scores, match_seasons = _completed_matches(session, args.teamid, season)
        if start_from_match is not None and season == min(seasons):
            # Filter to matches at or after the first active match in this season
            if start_from_time is not None and first_season_schedule:
                completed = [
                    m
                    for m in completed
                    if m in first_season_schedule
                    and first_season_schedule[m] >= start_from_time
                ]
            else:
                completed = [m for m in completed if m >= start_from_match]
        total_matches += len(completed)
        task_id = None
        if progress:
            task_id = progress.add_task(f"Season {season}", total=len(completed))
        for mid in completed:
            try:
                play_by_play = build_play_by_play_export(mid, get_xml_text(mid))
                perspective_rows = extract_team_perspective_moments(
                    mid,
                    play_by_play,
                    season=season,
                    match_type=match_types.get(mid),
                    final_score=match_scores.get(mid),
                )
            except Exception:
                skipped += 1
                if progress and task_id is not None:
                    progress.advance(task_id)
                continue
            total_hits += len({row.moment_id for row in perspective_rows})
            total_inserted += _save_hits(
                str(db_path),
                [row.to_dict() for row in perspective_rows],
            )
            if progress and task_id is not None:
                progress.advance(task_id)

    if progress:
        progress.__exit__(None, None, None)

    print(f"seasons: {','.join(str(s) for s in seasons)}")
    print(f"matches_scanned: {total_matches}")
    print(f"buzzerbeaters_found: {total_hits}")
    print(f"rows_inserted: {total_inserted}")
    if skipped:
        print(f"matches_skipped: {skipped}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any


REGULATION_SECONDS = 2880
OVERTIME_SECONDS = 300
BUZZERBEATER_PREFIX = "A buzzerbeater for "
PERIOD_END_WINDOW_SECONDS = 5
# Court image is 368px wide and baskets are at x=21 and x=347 (326px apart).
# Real basket-to-basket distance is 83.5 ft (94 ft court - 2 * 5.25 ft).
FT_PER_PX = 83.5 / 326


@dataclass(frozen=True)
class Moment:
    moment_id: str
    kind: str
    match_id: str
    season: int | None
    match_type: str | None
    start_time: str | None
    period: str
    gameclock: int
    home_team_id: str | None
    home_team_name: str | None
    away_team_id: str | None
    away_team_name: str | None
    scoring_team_id: str | None
    scoring_team_name: str | None
    scoring_team_is_home: bool
    player_id: str | None
    player_name: str | None
    comment: str | None
    event_kind: str | None
    shot_type: str | None
    shot_type_label: str | None
    shot_result: str | None
    free_throw_type: str | None
    shot_x: int | None
    shot_y: int | None
    shot_distance_ft: float | None
    score_before_home: int | None
    score_before_away: int | None
    score_after_home: int | None
    score_after_away: int | None
    final_score_home: int | None
    final_score_away: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TeamPerspectiveMoment:
    record_id: str
    moment_id: str
    match_id: str
    season: int | None
    match_type: str | None
    start_time: str | None
    period: str
    gameclock: int
    team_id: str | None
    team_name: str | None
    opponent_id: str | None
    opponent_name: str | None
    perspective: str
    is_home: bool
    player_id: str | None
    player_name: str | None
    comment: str | None
    scoring_team_id: str | None
    scoring_team_name: str | None
    event_kind: str | None
    shot_type: str | None
    shot_type_label: str | None
    shot_result: str | None
    free_throw_type: str | None
    shot_x: int | None
    shot_y: int | None
    shot_distance_ft: float | None
    score_before_home: int | None
    score_before_away: int | None
    score_after_home: int | None
    score_after_away: int | None
    team_score_before: int | None
    opponent_score_before: int | None
    team_score_after: int | None
    opponent_score_after: int | None
    final_team_score: int | None
    final_opponent_score: int | None
    outcome_changed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_buzzerbeater_moments(
    match_id: int | str,
    play_by_play: dict[str, Any],
    *,
    boxscore: dict[str, Any] | None = None,
    season: int | None = None,
    match_type: str | None = None,
    start_time: str | None = None,
    final_score: tuple[int | None, int | None] | None = None,
) -> list[Moment]:
    home_team, away_team = _resolve_team_context(play_by_play, boxscore)
    player_names = _resolve_player_names(play_by_play, boxscore)
    events = _events(play_by_play)
    max_clock = max((_optional_int(event.get("gameclock")) or 0) for event in events) or REGULATION_SECONDS
    period_ends = _build_period_ends(max_clock)
    score_snapshots = _score_snapshots(events)
    resolved_match_type = match_type or _optional_str((boxscore or {}).get("type"))
    resolved_start_time = start_time or _optional_str((boxscore or {}).get("startTime"))
    final_score_home, final_score_away = _resolve_final_scores(
        play_by_play,
        boxscore,
        final_score,
    )

    moments: list[Moment] = []
    for index, event in enumerate(events):
        if not _has_buzzerbeater_comment(event):
            continue
        clock = _optional_int(event.get("gameclock"))
        if clock is None:
            continue
        period_end = _matching_period_end(clock, period_ends)
        if period_end is None:
            continue
        team_index = _team_index(event.get("attacking_team"))
        if team_index is None:
            team_index = _team_index(event.get("team"))
        if team_index not in (0, 1):
            continue
        linked_index = _find_linked_scoring_event(
            events,
            score_snapshots,
            team_index=team_index,
            candidate_index=index,
            period_end=period_end,
        )
        if linked_index is None:
            continue
        linked_event = events[linked_index]
        before_score, after_score = score_snapshots.get(linked_index, ((None, None), (None, None)))
        player_id = _optional_str(linked_event.get("attacker")) or _optional_str(event.get("attacker"))
        comment = _buzzerbeater_comment(event)
        payload = {
            "gameclock": clock,
            "matchId": str(match_id),
            "period": _period_label_from_end(period_end, period_ends),
            "playerId": player_id,
            "scoringTeamId": home_team["id"] if team_index == 0 else away_team["id"],
        }
        moment_id = f"moment_{hashlib.sha1(json.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest()[:16]}"
        shot_x = _optional_int(linked_event.get("shot_pos_x"))
        shot_y = _optional_int(linked_event.get("shot_pos_y"))
        shot_distance_ft = _shot_distance_ft(team_index, shot_x, shot_y)
        moments.append(
            Moment(
                moment_id=moment_id,
                kind="BUZZERBEATER",
                match_id=str(match_id),
                season=season,
                match_type=resolved_match_type,
                start_time=resolved_start_time,
                period=_period_label_from_end(period_end, period_ends),
                gameclock=clock,
                home_team_id=home_team["id"],
                home_team_name=home_team["name"],
                away_team_id=away_team["id"],
                away_team_name=away_team["name"],
                scoring_team_id=home_team["id"] if team_index == 0 else away_team["id"],
                scoring_team_name=home_team["name"] if team_index == 0 else away_team["name"],
                scoring_team_is_home=team_index == 0,
                player_id=player_id,
                player_name=player_names.get((team_index, player_id)) if player_id else None,
                comment=comment,
                event_kind=_event_kind(linked_event),
                shot_type=_optional_str(linked_event.get("shot_type")),
                shot_type_label=_shot_type_label(linked_event.get("shot_type")),
                shot_result=_optional_str(linked_event.get("shot_result")),
                free_throw_type=_optional_str(linked_event.get("free_throw_type")),
                shot_x=shot_x,
                shot_y=shot_y,
                shot_distance_ft=shot_distance_ft,
                score_before_home=before_score[0],
                score_before_away=before_score[1],
                score_after_home=after_score[0],
                score_after_away=after_score[1],
                final_score_home=final_score_home,
                final_score_away=final_score_away,
            )
        )

    return moments


def extract_team_perspective_moments(
    match_id: int | str,
    play_by_play: dict[str, Any],
    *,
    boxscore: dict[str, Any] | None = None,
    season: int | None = None,
    match_type: str | None = None,
    start_time: str | None = None,
    final_score: tuple[int | None, int | None] | None = None,
) -> list[TeamPerspectiveMoment]:
    rows: list[TeamPerspectiveMoment] = []
    for moment in extract_buzzerbeater_moments(
        match_id,
        play_by_play,
        boxscore=boxscore,
        season=season,
        match_type=match_type,
        start_time=start_time,
        final_score=final_score,
    ):
        rows.extend(project_team_perspective_moments(moment))
    return rows


def project_team_perspective_moments(moment: Moment) -> list[TeamPerspectiveMoment]:
    rows: list[TeamPerspectiveMoment] = []
    teams = [
        (
            moment.home_team_id,
            moment.home_team_name,
            moment.away_team_id,
            moment.away_team_name,
            True,
        ),
        (
            moment.away_team_id,
            moment.away_team_name,
            moment.home_team_id,
            moment.home_team_name,
            False,
        ),
    ]
    for team_id, team_name, opponent_id, opponent_name, is_home in teams:
        team_score_before, opponent_score_before = _project_scores(
            is_home,
            moment.score_before_home,
            moment.score_before_away,
        )
        team_score_after, opponent_score_after = _project_scores(
            is_home,
            moment.score_after_home,
            moment.score_after_away,
        )
        final_team_score, final_opponent_score = _project_scores(
            is_home,
            moment.final_score_home,
            moment.final_score_away,
        )
        perspective = "FOR" if team_id == moment.scoring_team_id else "AGAINST"
        rows.append(
            TeamPerspectiveMoment(
                record_id=f"{moment.moment_id}:{team_id}",
                moment_id=moment.moment_id,
                match_id=moment.match_id,
                season=moment.season,
                match_type=moment.match_type,
                start_time=moment.start_time,
                period=moment.period,
                gameclock=moment.gameclock,
                team_id=team_id,
                team_name=team_name,
                opponent_id=opponent_id,
                opponent_name=opponent_name,
                perspective=perspective,
                is_home=is_home,
                player_id=moment.player_id,
                player_name=moment.player_name,
                comment=moment.comment,
                scoring_team_id=moment.scoring_team_id,
                scoring_team_name=moment.scoring_team_name,
                event_kind=moment.event_kind,
                shot_type=moment.shot_type,
                shot_type_label=moment.shot_type_label,
                shot_result=moment.shot_result,
                free_throw_type=moment.free_throw_type,
                shot_x=moment.shot_x,
                shot_y=moment.shot_y,
                shot_distance_ft=moment.shot_distance_ft,
                score_before_home=moment.score_before_home,
                score_before_away=moment.score_before_away,
                score_after_home=moment.score_after_home,
                score_after_away=moment.score_after_away,
                team_score_before=team_score_before,
                opponent_score_before=opponent_score_before,
                team_score_after=team_score_after,
                opponent_score_after=opponent_score_after,
                final_team_score=final_team_score,
                final_opponent_score=final_opponent_score,
                outcome_changed=_outcome_changed(
                    moment.period,
                    team_score_before,
                    opponent_score_before,
                    team_score_after,
                    opponent_score_after,
                ),
            )
        )
    return rows


def _events(play_by_play: dict[str, Any]) -> list[dict[str, Any]]:
    values = play_by_play.get("events")
    return values if isinstance(values, list) else []


def _resolve_team_context(
    play_by_play: dict[str, Any],
    boxscore: dict[str, Any] | None,
) -> tuple[dict[str, str | None], dict[str, str | None]]:
    home = (boxscore or {}).get("homeTeam") if isinstance(boxscore, dict) else None
    away = (boxscore or {}).get("awayTeam") if isinstance(boxscore, dict) else None
    pbp_home = play_by_play.get("teamHome") if isinstance(play_by_play, dict) else None
    pbp_away = play_by_play.get("teamAway") if isinstance(play_by_play, dict) else None
    return (
        {
            "id": _optional_str((home or {}).get("id")) or _optional_str((pbp_home or {}).get("id")),
            "name": _optional_str((home or {}).get("teamName")) or _optional_str((pbp_home or {}).get("name")),
        },
        {
            "id": _optional_str((away or {}).get("id")) or _optional_str((pbp_away or {}).get("id")),
            "name": _optional_str((away or {}).get("teamName")) or _optional_str((pbp_away or {}).get("name")),
        },
    )


def _resolve_player_names(
    play_by_play: dict[str, Any],
    boxscore: dict[str, Any] | None,
) -> dict[tuple[int, str], str]:
    names: dict[tuple[int, str], str] = {}
    for team_index, team_key, box_key in (
        (0, "teamHome", "homeTeam"),
        (1, "teamAway", "awayTeam"),
    ):
        team = play_by_play.get(team_key) or {}
        for player in team.get("players") or []:
            player_id = _optional_str(player.get("id"))
            player_name = _optional_str(player.get("name"))
            if player_id and player_name:
                names[(team_index, player_id)] = player_name
        if not isinstance(boxscore, dict):
            continue
        for player in ((boxscore.get(box_key) or {}).get("players") or []):
            player_id = _optional_str(player.get("id"))
            player_name = _optional_str(player.get("fullName"))
            if player_id and player_name and (team_index, player_id) not in names:
                names[(team_index, player_id)] = player_name
    return names


def _resolve_final_scores(
    play_by_play: dict[str, Any],
    boxscore: dict[str, Any] | None,
    final_score: tuple[int | None, int | None] | None,
) -> tuple[int | None, int | None]:
    if final_score is not None:
        return final_score
    if isinstance(boxscore, dict):
        return (
            _optional_int((boxscore.get("homeTeam") or {}).get("score")),
            _optional_int((boxscore.get("awayTeam") or {}).get("score")),
        )
    team_home = play_by_play.get("teamHome") or {}
    team_away = play_by_play.get("teamAway") or {}
    return (
        _optional_int((((team_home.get("stats") or {}).get("total") or {}).get("pts"))),
        _optional_int((((team_away.get("stats") or {}).get("total") or {}).get("pts"))),
    )


def _build_period_ends(max_clock: int) -> list[int]:
    quarter_end = 720
    period_ends = [quarter_end * index for index in range(1, 5) if quarter_end * index <= max_clock]
    if max_clock > REGULATION_SECONDS:
        extra_seconds = max_clock - REGULATION_SECONDS
        overtime_count = (extra_seconds + OVERTIME_SECONDS - 1) // OVERTIME_SECONDS
        period_ends.extend(
            REGULATION_SECONDS + OVERTIME_SECONDS * index
            for index in range(1, overtime_count + 1)
        )
    return period_ends or [REGULATION_SECONDS]


def _matching_period_end(clock: int, period_ends: list[int]) -> int | None:
    for period_end in period_ends:
        if period_end - PERIOD_END_WINDOW_SECONDS <= clock <= period_end:
            return period_end
    return None


def _period_label_from_end(period_end: int, period_ends: list[int]) -> str:
    period_index = period_ends.index(period_end) + 1
    if period_index <= 4:
        return f"Q{period_index}"
    return f"OT{period_index - 4}"


def _has_buzzerbeater_comment(event: dict[str, Any]) -> bool:
    return _buzzerbeater_comment(event) is not None


def _buzzerbeater_comment(event: dict[str, Any]) -> str | None:
    comments = event.get("comments")
    if not isinstance(comments, list):
        return None
    for comment in comments:
        if isinstance(comment, str) and comment.startswith(BUZZERBEATER_PREFIX) and comment.endswith("!"):
            return comment
    return None


def _find_linked_scoring_event(
    events: list[dict[str, Any]],
    score_snapshots: dict[int, tuple[tuple[int | None, int | None], tuple[int | None, int | None]]],
    *,
    team_index: int,
    candidate_index: int,
    period_end: int,
) -> int | None:
    window_start = period_end - PERIOD_END_WINDOW_SECONDS
    for index in range(candidate_index, -1, -1):
        event = events[index]
        clock = _optional_int(event.get("gameclock"))
        if clock is None:
            continue
        if clock < window_start:
            break
        if clock > period_end:
            continue
        if _team_index(event.get("attacking_team")) != team_index:
            continue
        if index in score_snapshots:
            return index
    return None


def _score_snapshots(
    events: list[dict[str, Any]],
) -> dict[int, tuple[tuple[int | None, int | None], tuple[int | None, int | None]]]:
    scores = [0, 0]
    snapshots: dict[int, tuple[tuple[int | None, int | None], tuple[int | None, int | None]]] = {}
    for index, event in enumerate(events):
        team_index = _team_index(event.get("attacking_team"))
        points = _event_points(event)
        if team_index not in (0, 1) or points <= 0:
            continue
        before_score = (scores[0], scores[1])
        scores[team_index] += points
        after_score = (scores[0], scores[1])
        snapshots[index] = (before_score, after_score)
    return snapshots


def _event_points(event: dict[str, Any]) -> int:
    event_kind = _event_kind(event)
    shot_result = _optional_str(event.get("shot_result"))
    if event_kind == "shot" and shot_result in {"SCORED", "SCORED_WITH_FOUL", "GOALTEND"}:
        shot_type = _optional_str(event.get("shot_type")) or ""
        return 3 if shot_type.startswith("THREE_POINTER") else 2
    if event_kind == "free_throw" and shot_result == "SCORED":
        return 1
    return 0


def _shot_distance_ft(team_index: int, shot_x: int | None, shot_y: int | None) -> float | None:
    if shot_x is None or shot_y is None:
        return None
    basket_x, basket_y = (347, 96) if team_index == 0 else (21, 96)
    dx = shot_x - basket_x
    dy = shot_y - basket_y
    return math.sqrt(dx * dx + dy * dy) * FT_PER_PX


def _event_kind(event: dict[str, Any]) -> str | None:
    return _optional_str(event.get("event_type"))


def _shot_type_label(shot_type: Any) -> str | None:
    value = _optional_str(shot_type)
    if not value:
        return None
    return value.replace("_", " ").lower()


def _project_scores(
    is_home: bool,
    home_score: int | None,
    away_score: int | None,
) -> tuple[int | None, int | None]:
    if is_home:
        return home_score, away_score
    return away_score, home_score


def _outcome_changed(
    period: str,
    team_score_before: int | None,
    opponent_score_before: int | None,
    team_score_after: int | None,
    opponent_score_after: int | None,
) -> bool:
    if not period.upper().startswith(("Q4", "OT")):
        return False
    if None in (team_score_before, opponent_score_before, team_score_after, opponent_score_after):
        return False
    before_margin = int(team_score_before) - int(opponent_score_before)
    after_margin = int(team_score_after) - int(opponent_score_after)
    return (
        (before_margin > 0 and after_margin <= 0)
        or (before_margin == 0 and after_margin != 0)
        or (before_margin < 0 and after_margin >= 0)
    )


def _team_index(value: Any) -> int | None:
    parsed = _optional_int(value)
    return parsed if parsed in (0, 1) else None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    return str(value)

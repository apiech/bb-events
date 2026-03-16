from pathlib import Path

from bb_xml_client import get_client
from team import Team
from player import Player
from stats import *


def _int_value(value) -> int:
    if value is None:
        return 0
    return int(value)


class BBApi:
    def __init__(self, login=None, password=None):
        self.login = login
        self.password = password
        self.logged_in = login is not None and password is not None
        self._client = get_client(login, password) if self.logged_in else None

    def _require_client(self):
        if self._client is None:
            raise RuntimeError("BBApi requires login and password for XML API access")
        return self._client

    def arena(self, teamid=0):
        arena = self._require_client().get_arena(teamid or None)
        arena_name = arena.name
        arena_seats, arena_expansion = {}, {}
        for seat_name, seat in arena.seats.items():
            arena_seats[seat_name] = (
                _int_value(seat.capacity),
                {
                    "price": _int_value(seat.price),
                    "nextPrice": _int_value(seat.next_price),
                },
            )
        if arena.expansion is not None:
            arena_expansion["daysLeft"] = _int_value(arena.expansion.days_left)
            for seat_name, seat_count in arena.expansion.sections.items():
                arena_expansion[seat_name] = seat_count

        return arena_name, arena_seats, arena_expansion

    def get_xml_boxscore(self, matchid) -> str:
        path = Path("matches") / f"boxscore_{matchid}.xml"
        if path.exists():
            return path.read_text(encoding="utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        text = self._require_client().request_xml("boxscore.aspx", {"matchid": matchid})
        path.write_text(text, encoding="utf-8")
        return text

    def get_xml_standings(self, leagueid: int, season: int) -> str:
        path = Path("matches") / f"standings_{leagueid}_{season}.xml"
        if path.exists():
            return path.read_text(encoding="utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        text = self._require_client().request_xml(
            "standings.aspx",
            {"leagueid": str(leagueid), "season": str(season)},
        )
        path.write_text(text, encoding="utf-8")
        return text

    def get_xml_schedule(self, teamid, season) -> str:
        path = Path("matches") / f"schedule_{teamid}_{season}.xml"
        if path.exists():
            return path.read_text(encoding="utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        text = self._require_client().request_xml(
            "schedule.aspx",
            {"teamid": teamid, "season": season},
        )
        path.write_text(text, encoding="utf-8")
        return text

    def player(self, playerid) -> str:
        response = self._require_client().get_player(playerid)
        return response.best_position or ""

    def strategy(self, matchid=0):
        data = self._require_client().get_boxscore(matchid or None)
        return (
            data.away_team.off_strategy or "",
            data.away_team.def_strategy or "",
            data.home_team.off_strategy or "",
            data.home_team.def_strategy or "",
        )

    def boxscore(self, matchid=0) -> list[Team]:
        response = self._require_client().get_boxscore(matchid or None)
        bb_teams = [Team(), Team()]
        for bb_team, source_team in zip(bb_teams, [response.away_team, response.home_team]):
            bb_team.id = _int_value(source_team.id)
            bb_team.name = source_team.team_name or ""
            bb_team.off_strategy = source_team.off_strategy or ""
            bb_team.def_strategy = source_team.def_strategy or ""
            for _ in range(len(source_team.partial_scores)):
                bb_team.push_stat_sheet()
            for num, pts in enumerate(source_team.partial_scores):
                bb_team.stats.qtr[num].sheet[Statistic.Points] = pts

            totals = source_team.team_totals

            def add_team_stat(stat: Statistic, key: str):
                bb_team.stats.full.sheet[stat] = _int_value(totals.get(key))

            add_team_stat(Statistic.Points, "pts")
            add_team_stat(Statistic.FieldGoalsAtt, "fga")
            add_team_stat(Statistic.FieldGoalsMade, "fgm")
            add_team_stat(Statistic.ThreePointsAtt, "tpa")
            add_team_stat(Statistic.ThreePointsMade, "tpm")
            add_team_stat(Statistic.FreeThrowsAtt, "fta")
            add_team_stat(Statistic.FreeThrowsMade, "ftm")
            add_team_stat(Statistic.OffRebounds, "oreb")
            bb_team.stats.full.sheet[Statistic.DefRebounds] = _int_value(totals.get("reb")) - _int_value(totals.get("oreb"))
            add_team_stat(Statistic.Assists, "ast")
            add_team_stat(Statistic.Turnovers, "to")
            add_team_stat(Statistic.Steals, "stl")
            add_team_stat(Statistic.Blocks, "blk")
            add_team_stat(Statistic.Fouls, "pf")

            for source_player in source_team.players:
                bb_player = Player()
                bb_player.id = _int_value(source_player.id)
                bb_player.name = " ".join(
                    part for part in [source_player.first_name, source_player.last_name] if part
                ).strip()
                minutes = source_player.minutes_by_position
                bb_player.stats.full.sheet[Statistic.SecsPG] = _int_value(minutes.get("PG")) * 60
                bb_player.stats.full.sheet[Statistic.SecsSG] = _int_value(minutes.get("SG")) * 60
                bb_player.stats.full.sheet[Statistic.SecsSF] = _int_value(minutes.get("SF")) * 60
                bb_player.stats.full.sheet[Statistic.SecsPF] = _int_value(minutes.get("PF")) * 60
                bb_player.stats.full.sheet[Statistic.SecsC] = _int_value(minutes.get("C")) * 60
                perf = source_player.performance
                bb_player.stats.full.sheet[Statistic.Points] = _int_value(perf.get("pts"))
                bb_player.stats.full.sheet[Statistic.FieldGoalsAtt] = _int_value(perf.get("fga"))
                bb_player.stats.full.sheet[Statistic.FieldGoalsMade] = _int_value(perf.get("fgm"))
                bb_player.stats.full.sheet[Statistic.ThreePointsAtt] = _int_value(perf.get("tpa"))
                bb_player.stats.full.sheet[Statistic.ThreePointsMade] = _int_value(perf.get("tpm"))
                bb_player.stats.full.sheet[Statistic.FreeThrowsAtt] = _int_value(perf.get("fta"))
                bb_player.stats.full.sheet[Statistic.FreeThrowsMade] = _int_value(perf.get("ftm"))
                bb_player.stats.full.sheet[Statistic.OffRebounds] = _int_value(perf.get("oreb"))
                bb_player.stats.full.sheet[Statistic.DefRebounds] = _int_value(perf.get("reb")) - _int_value(perf.get("oreb"))
                bb_player.stats.full.sheet[Statistic.Assists] = _int_value(perf.get("ast"))
                bb_player.stats.full.sheet[Statistic.Turnovers] = _int_value(perf.get("to"))
                bb_player.stats.full.sheet[Statistic.Steals] = _int_value(perf.get("stl"))
                bb_player.stats.full.sheet[Statistic.Blocks] = _int_value(perf.get("blk"))
                bb_player.stats.full.sheet[Statistic.Fouls] = _int_value(perf.get("pf"))
                bb_team.players.append(bb_player)
        return bb_teams

    def standings(self, league_id: int, season: int):
        data = self._require_client().get_standings(league_id=league_id, season=season)
        team_ids = []
        for conference in data.conferences:
            for team in conference.teams:
                if team.id is not None:
                    team_ids.append(str(team.id))
        return team_ids

    def schedule(self, team_id, season):
        data = self._require_client().get_schedule(team_id=team_id, season=season)
        return [
            str(match.id)
            for match in data.matches
            if match.id is not None and (match.type or "").startswith("league")
        ]


def prefetch_data(
    username: str, password: str, leagueid_: int, season_from: int, season_to: int
):
    api = BBApi(username, password)

    unique_ids = set[str]()

    leagueids = [
        1,  # USA
        86,  # Argentina,
        107,  # Brasil
        128,  # Canada
        149,  # China
        170,  # Turkiye
        191,  # Espana
        212,  # Deutschland
        254,  # Italia
        275,  # France
        296,  # Hellas
        893,  # Belgium
        978,  # England
        999,  # Isreal
        1020,  # Nederland
        1062,  # Portugal
        1083,  # Rossiya
        1104,  # Lietuva
        1277,  # Srbija
        2083,  # Polska
    ]

    # [ 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15, 16, 18, 19, 20, 29, 58]
    season = 59

    for leagueid in leagueids:
        team_ids = api.standings(leagueid, season)
        print(f"Season {season}: teams: {len(team_ids)}")
        for team_id in team_ids:
            match_ids = api.schedule(team_id, season)
            unique_ids.update(match_ids)
            print(f"LeagueID: {leagueid}, Season {season}: matches: {len(match_ids)}")

    with open("uids-various.txt", "w", encoding='utf-8') as f:
        for index, uid in enumerate(unique_ids):
            print(f"Fetch {uid} ({index+1}/{len(unique_ids)})")
            api.boxscore(uid)

            f.write(str(uid) + "\n")

    print(unique_ids)
    print(len(unique_ids))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--leagueid", type=int, required=True)
    parser.add_argument("--season-from", type=int, required=True)
    parser.add_argument("--season-to", type=int, required=True)
    args = parser.parse_args()

    prefetch_data(
        args.username, args.password, args.leagueid, args.season_from, args.season_to
    )

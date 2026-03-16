import unittest

from moments import extract_buzzerbeater_moments, extract_team_perspective_moments


def _build_play_by_play(*, final_clock: int) -> dict:
    return {
        "teamHome": {
            "id": "home-1",
            "name": "Alpha",
            "players": [
                {
                    "id": "p-home",
                    "name": "Alice Alpha",
                }
            ],
        },
        "teamAway": {
            "id": "away-1",
            "name": "Beta",
            "players": [
                {
                    "id": "p-away",
                    "name": "Barry Beta",
                }
            ],
        },
        "events": [
            {
                "attacking_team": 1,
                "attacker": "p-away",
                "event_type": "free_throw",
                "gameclock": 100,
                "shot_result": "SCORED",
            },
            {
                "attacking_team": 0,
                "attacker": "p-home",
                "comments": ["A buzzerbeater for Alpha!"],
                "event_type": "shot",
                "gameclock": final_clock,
                "shot_pos_x": 300,
                "shot_pos_y": 96,
                "shot_result": "SCORED",
                "shot_type": "ShotType.TWO_POINTER_ELBOW",
            },
        ],
    }


def _build_boxscore(*, home_score: int, away_score: int) -> dict:
    return {
        "homeTeam": {
            "id": "home-1",
            "score": home_score,
            "teamName": "Alpha",
        },
        "awayTeam": {
            "id": "away-1",
            "score": away_score,
            "teamName": "Beta",
        },
        "matchId": "match-1",
        "startTime": "2026-03-15T20:00:00.000Z",
        "type": "League",
    }


class MomentsTests(unittest.TestCase):
    def test_extract_team_perspective_moments_emits_for_and_against_rows(self) -> None:
        rows = extract_team_perspective_moments(
            "match-1",
            _build_play_by_play(final_clock=2880),
            boxscore=_build_boxscore(home_score=2, away_score=1),
            season=72,
        )

        self.assertEqual(len(rows), 2)
        by_perspective = {row.perspective: row for row in rows}
        self.assertEqual(set(by_perspective), {"FOR", "AGAINST"})
        self.assertEqual(by_perspective["FOR"].team_id, "home-1")
        self.assertEqual(by_perspective["FOR"].team_score_before, 0)
        self.assertEqual(by_perspective["FOR"].opponent_score_before, 1)
        self.assertEqual(by_perspective["FOR"].team_score_after, 2)
        self.assertEqual(by_perspective["AGAINST"].team_id, "away-1")
        self.assertEqual(by_perspective["AGAINST"].team_score_before, 1)
        self.assertEqual(by_perspective["AGAINST"].team_score_after, 1)
        self.assertEqual(by_perspective["AGAINST"].opponent_score_after, 2)

    def test_outcome_changed_only_applies_in_q4_and_ot(self) -> None:
        q2_rows = extract_team_perspective_moments(
            "match-q2",
            _build_play_by_play(final_clock=1440),
            boxscore=_build_boxscore(home_score=2, away_score=1),
        )
        ot_rows = extract_team_perspective_moments(
            "match-ot",
            _build_play_by_play(final_clock=3180),
            boxscore=_build_boxscore(home_score=2, away_score=1),
        )

        self.assertTrue(all(row.outcome_changed is False for row in q2_rows))
        self.assertTrue(all(row.outcome_changed is True for row in ot_rows))

    def test_buzzerbeater_moment_ids_are_stable(self) -> None:
        first = extract_buzzerbeater_moments(
            "match-1",
            _build_play_by_play(final_clock=2880),
            boxscore=_build_boxscore(home_score=2, away_score=1),
            season=72,
        )
        second = extract_buzzerbeater_moments(
            "match-1",
            _build_play_by_play(final_clock=2880),
            boxscore=_build_boxscore(home_score=2, away_score=1),
            season=72,
        )

        self.assertEqual(len(first), 1)
        self.assertEqual([row.moment_id for row in first], [row.moment_id for row in second])


if __name__ == "__main__":
    unittest.main()

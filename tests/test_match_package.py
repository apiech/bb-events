import unittest
from pathlib import Path

from match_package import (
    DEFAULT_PARSER_VERSION,
    build_match_package,
    compute_content_hash,
    load_json,
)


ROOT = Path(__file__).resolve().parents[1]
PLAY_BY_PLAY_FIXTURE = ROOT / "123786926.json"
BOXSCORE_FIXTURE = ROOT / "tests" / "fixtures" / "123786926_boxscore.json"


class MatchPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.play_by_play = load_json(PLAY_BY_PLAY_FIXTURE)
        cls.boxscore = load_json(BOXSCORE_FIXTURE)

    def test_build_match_package_embeds_summary_and_hash(self) -> None:
        package = build_match_package(
            123786926,
            season=72,
            boxscore=self.boxscore,
            play_by_play=self.play_by_play,
            raw_boxscore_key="raw/123786926/boxscore.xml",
            raw_report_key="raw/123786926/report.xml",
        )

        self.assertEqual(package["schemaVersion"], "MatchPackageV1")
        self.assertEqual(package["matchId"], "123786926")
        self.assertEqual(package["parserVersion"], DEFAULT_PARSER_VERSION)
        self.assertEqual(
            package["match"],
            {
                "matchId": "123786926",
                "season": 72,
                "type": "League",
                "startTime": "2026-03-15T20:00:00.000Z",
                "endTime": "2026-03-15T21:55:00.000Z",
                "neutral": False,
                "eventCount": len(self.play_by_play["events"]),
                "homeTeam": {
                    "id": "163730",
                    "teamName": "Bulls Chicago 94",
                    "score": 59,
                },
                "awayTeam": {
                    "id": "235159",
                    "teamName": "Pony Slaystation",
                    "score": 123,
                },
            },
        )
        self.assertEqual(
            package["sourceArtifacts"],
            {
                "boxscoreKey": "raw/123786926/boxscore.xml",
                "reportKey": "raw/123786926/report.xml",
            },
        )
        self.assertEqual(package["ingestMetadata"]["season"], 72)
        self.assertIsInstance(package["ingestMetadata"]["generatedAt"], str)
        self.assertTrue(package["contentHash"].startswith("sha256:"))

    def test_content_hash_is_stable_for_identical_inputs(self) -> None:
        base_payload = {
            "schemaVersion": "MatchPackageV1",
            "matchId": "123786926",
            "parserVersion": DEFAULT_PARSER_VERSION,
            "sourceArtifacts": {
                "boxscoreKey": None,
                "reportKey": None,
            },
            "match": {
                "matchId": "123786926",
                "season": 72,
            },
            "boxscore": self.boxscore,
            "playByPlay": self.play_by_play,
            "ingestMetadata": {
                "season": 72,
            },
        }

        self.assertEqual(
            compute_content_hash(base_payload),
            compute_content_hash(base_payload),
        )

    def test_content_hash_changes_when_parser_version_changes(self) -> None:
        default_package = build_match_package(
            123786926,
            season=72,
            boxscore=self.boxscore,
            play_by_play=self.play_by_play,
        )
        upgraded_package = build_match_package(
            123786926,
            season=72,
            boxscore=self.boxscore,
            play_by_play=self.play_by_play,
            parser_version="bb-events-match-package-v2",
        )

        self.assertNotEqual(
            default_package["contentHash"],
            upgraded_package["contentHash"],
        )


if __name__ == "__main__":
    unittest.main()

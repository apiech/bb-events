import argparse
import contextlib
import io
import json

from match_package import build_play_by_play_export
from moments import Moment, extract_buzzerbeater_moments
from main import get_xml_text


def find_buzzerbeaters(matchid: int) -> list[Moment]:
    text = get_xml_text(matchid)
    # Suppress parser debug chatter from the legacy report path.
    with contextlib.redirect_stdout(io.StringIO()):
        play_by_play = build_play_by_play_export(matchid, text)
    return extract_buzzerbeater_moments(matchid, play_by_play)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matchid", type=int, required=True, help="Match ID")
    parser.add_argument("--json", action="store_true", help="Print results as JSON")
    parser.add_argument(
        "--details",
        action="store_true",
        help="Show linked scoring details",
    )
    args = parser.parse_args()

    hits = find_buzzerbeaters(args.matchid)

    if args.json:
        print(json.dumps([hit.to_dict() for hit in hits], indent=2))
        return

    print(f"buzzerbeaters: {len(hits)}")
    for hit in hits:
        team_name = hit.scoring_team_name or "Unknown Team"
        line = f"- {team_name} {hit.period} buzzerbeater"
        if args.details:
            if hit.event_kind == "shot":
                line += (
                    f" | shot_type={hit.shot_type}"
                    f" shot_label={hit.shot_type_label}"
                    f" shot_result={hit.shot_result}"
                    f" pos=({hit.shot_x},{hit.shot_y})"
                    f" dist_ft={hit.shot_distance_ft}"
                    f" score={hit.score_before_home}-{hit.score_before_away}"
                    f"→{hit.score_after_home}-{hit.score_after_away}"
                )
            elif hit.event_kind == "free_throw":
                line += (
                    f" | free_throw_type={hit.free_throw_type}"
                    f" shot_result={hit.shot_result}"
                    f" score={hit.score_before_home}-{hit.score_before_away}"
                    f"→{hit.score_after_home}-{hit.score_after_away}"
                )
            else:
                line += " | scoring_event=unknown"
        print(line)


if __name__ == "__main__":
    main()

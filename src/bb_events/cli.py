from __future__ import annotations

import buzzerbeater_descriptions as buzzerbeater_descriptions_module
import buzzerbeaters as buzzerbeaters_module
import event as event_module
import main as main_module
import match_package as match_package_module
import team_buzzerbeaters as team_buzzerbeaters_module
import team_info as team_info_module
import team_shot_distance_hist as team_shot_distance_hist_module


def main() -> None:
    main_module.main()


def shotchart() -> None:
    event_module.shotchart_main()


def buzzerbeaters() -> None:
    buzzerbeaters_module.main()


def team_info() -> None:
    team_info_module.main()


def team_buzzerbeaters() -> None:
    team_buzzerbeaters_module.main()


def team_shot_distance_hist() -> None:
    team_shot_distance_hist_module.main()


def buzzerbeater_descriptions() -> None:
    buzzerbeater_descriptions_module.main()


def match_package() -> None:
    match_package_module.main()

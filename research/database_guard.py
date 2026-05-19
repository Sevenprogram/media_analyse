from typing import Final

import config


RESEARCH_SQL_SAVE_OPTIONS: Final[set[str]] = {"sqlite", "postgres", "mysql", "db"}


class ResearchDatabaseNotConfigured(RuntimeError):
    pass


def is_research_database_enabled(save_option: str | None = None) -> bool:
    option = save_option if save_option is not None else getattr(config, "SAVE_DATA_OPTION", None)
    return option in RESEARCH_SQL_SAVE_OPTIONS


def research_database_error_message(save_option: str | None = None) -> str:
    option = save_option if save_option is not None else getattr(config, "SAVE_DATA_OPTION", None)
    supported = ", ".join(sorted(RESEARCH_SQL_SAVE_OPTIONS))
    return (
        "Research module requires SQL storage. "
        f"Set SAVE_DATA_OPTION to one of: {supported}. Current value: {option}"
    )


def assert_research_database_enabled(save_option: str | None = None) -> None:
    if not is_research_database_enabled(save_option):
        raise ResearchDatabaseNotConfigured(research_database_error_message(save_option))

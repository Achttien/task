import logging
import os


def configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose or os.getenv("GCALSHEET_AGENT_DEBUG") == "1" else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

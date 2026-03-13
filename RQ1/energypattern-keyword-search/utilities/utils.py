from datetime import datetime

from constants.abs_paths import AbsDirPath


def create_logger_path(prefix: str) -> str:
    return AbsDirPath.LOGS / f"{prefix}.{datetime.now().strftime('%Y-%m-%dT%H-%M-%S')}.log"

"""Entrypoint: python -m finlytics"""

import copy

import uvicorn
from uvicorn.config import LOGGING_CONFIG


def _log_config() -> dict:
    config = copy.deepcopy(LOGGING_CONFIG)
    for formatter_name in ("default", "access"):
        formatter = config["formatters"][formatter_name]
        formatter["fmt"] = f"%(asctime)s {formatter['fmt']}"
        formatter["datefmt"] = "%Y-%m-%d %H:%M:%S"

    config["loggers"][""] = {
        "handlers": ["default"],
        "level": "INFO",
    }
    return config


def main() -> None:
    uvicorn.run(
        "finlytics.app:app",
        host="0.0.0.0",
        port=7777,
        log_config=_log_config(),
    )


if __name__ == "__main__":
    main()

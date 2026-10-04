"""Entrypoint: python -m finlytics"""

import copy

import uvicorn
from uvicorn.config import LOGGING_CONFIG

from finlytics.api.middleware import RequestIdFilter


def _log_config() -> dict:
    config = copy.deepcopy(LOGGING_CONFIG)
    # The filter sits on the handlers, not a logger, so records propagated from
    # any library logger get the attribute the format string needs.
    config["filters"] = {"request_id": {"()": RequestIdFilter}}
    for name in ("default", "access"):
        formatter = config["formatters"][name]
        formatter["fmt"] = f"%(asctime)s [%(request_id)s] {formatter['fmt']}"
        formatter["datefmt"] = "%Y-%m-%d %H:%M:%S"
        config["handlers"][name]["filters"] = ["request_id"]

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

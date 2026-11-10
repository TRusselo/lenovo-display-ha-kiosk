"""Turn a stock Lenovo Smart Display 8 into a degoogled Home Assistant kiosk."""

__version__ = "0.1.0"

# Where the docs live online. Change this one line if the repository moves.
DOCS_URL = "https://github.com/TRusselo/lenovo-display-ha-kiosk/blob/main"


def doc(path: str, section: str = "") -> str:
    """A doc named in a message: in the release zip next to the program, and online."""
    where = f"{path}, {section}" if section else path
    return f"{where} (in the download, or {DOCS_URL}/{path})"

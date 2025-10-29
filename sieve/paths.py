import tempfile
from pathlib import Path

PATH_BUILD = (Path(tempfile.gettempdir()) / "pandoc-sieve").resolve()

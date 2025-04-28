"""
Pandoc filter to process code blocks with class "mermaid" containing
diagrams into images.  Assumes that `mmdc` is in the path.
Images are put in a temporary directory.
"""

import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

from panflute import CodeBlock, Doc, Element, Image, Para, run_filter

PATH_BUILD = (Path(tempfile.gettempdir()) / "pandoc-sieve").resolve()
PATH_MERMAID = PATH_BUILD / "mermaid"


def sha1(x: str) -> str:
    return hashlib.sha1(x.encode(sys.getfilesystemencoding())).hexdigest()  # noqa: S324


def mermaid_compile(src: str, dst: Path) -> None:
    proc = subprocess.Popen(
        ["mmdc", "-i", "-", "-o", dst, "-w1000", "-H", "1600"],
        stdin=subprocess.PIPE,
        stdout=sys.stderr,
        stderr=sys.stderr,
        shell=True,
    )
    proc.communicate(input=src.encode("utf-8"))
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to compile mermaid code: {src}")


def mermaid(elem: Element, doc: Doc) -> Para | None:
    if type(elem) is CodeBlock and "mermaid" in elem.classes:
        code = elem.text

        # filetype = {"html": "png", "latex": "pdf"}.get(doc.format, "png")
        filetype = "png"
        PATH_MERMAID.mkdir(parents=True, exist_ok=True)

        outfile = (PATH_MERMAID / sha1(code)).with_suffix(f".{filetype}")

        mermaid_compile(code, outfile)
        print(f"Mermaid: {outfile}", file=sys.stderr)
        return Para(Image(url=str(outfile)))

    return None


def main_mermaid(doc=None):
    return run_filter(mermaid, doc=doc)

"""
Pandoc filter to process code blocks with class "mermaid" containing
diagrams into images.  Assumes that `mmdc` is in the path.
Images are put in a temporary directory.
"""

import hashlib
import subprocess
import sys
from pathlib import Path

import panflute
from panflute import Caption, CodeBlock, Doc, Element, Figure, Image, Plain, run_filter

from .paths import PATH_BUILD

PATH_MERMAID = PATH_BUILD / "mermaid"


def sha1(x: str) -> str:
    return hashlib.sha1(x.encode(sys.getfilesystemencoding())).hexdigest()  # noqa: S324


def mermaid_compile(src: str, dst: Path) -> None:
    proc = subprocess.Popen(
        ["mmdc", "-i", "-", "-o", dst, "-w", "1920", "-H", "1080", "-b", "transparent", "-f"],  # noqa: S607
        stdin=subprocess.PIPE,
        stdout=sys.stderr,
        stderr=sys.stderr,
        shell=True,
    )
    proc.communicate(input=src.encode("utf-8"))
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to compile mermaid code: {src}")


def mermaid(elem: Element, doc: Doc) -> Element | None:
    """Convert mermaid code blocks to images.

    ```mermaid {#ref-id caption="Diagram caption" alt="Diagram alt text" title="Diagram title"}
    graph TD;
        A-->B;
    ```
    """

    if type(elem) is CodeBlock and "mermaid" in elem.classes:
        code = elem.text
        filetype = {
            "html": "svg",
            "markdown": "svg",
            "pdf": "pdf",
            "latex": "pdf",
        }.get(doc.format, "png")

        PATH_MERMAID.mkdir(parents=True, exist_ok=True)
        outfile = (PATH_MERMAID / sha1(code)).with_suffix(f".{filetype}")

        mermaid_compile(code, outfile)
        print(f"Mermaid: {outfile}", file=sys.stderr)

        caption = (
            Caption(*panflute.convert_text(caption_text))
            if (caption_text := elem.attributes.pop("caption", None))
            else None
        )

        alt = (
            panflute.convert_text(alt_text)
            if (alt_text := elem.attributes.pop("alt", None))
            else panflute.convert_text(caption_text if caption_text else "Mermaid Diagram")
        )
        image = Image(
            # Convert alt Para to inlines
            *((alt[0].content) if alt is not None else ()),
            url=str(outfile),
            title=elem.attributes.pop("title", ""),
            attributes=elem.attributes,
            classes=elem.classes,
            identifier=elem.identifier if caption is not None else "",
        )

        if caption is not None:
            return Figure(
                Plain(image),
                caption=caption,
                identifier=elem.identifier,
            )
        return Plain(image)

    return None


def main(doc=None):
    return run_filter(mermaid, doc=doc)

import argparse
import io
import subprocess
import sys
import traceback
from collections.abc import Callable, Generator
from contextlib import contextmanager, suppress
from itertools import chain
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Concatenate

import yaml

from .paths import PATH_BUILD


def from_namespace[**A, R](func: Callable[Concatenate[A], R]) -> Callable[[argparse.Namespace], R]:
    def decorator(args: argparse.Namespace) -> R:
        return func(**vars(args))  # pyright: ignore[reportCallIssue]

    return decorator


def frontmatter(markdown: str) -> dict[str, Any]:
    MARKER = "---"
    markdown = markdown.strip()
    if markdown.startswith(MARKER):
        mapping = markdown[len(MARKER) : markdown.find(MARKER, len(MARKER))]
        return yaml.safe_load(mapping)
    return {}


def pandoc(src: Path, dest: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["pandoc", *args, src, "-o", dest],
        capture_output=True,
        encoding="utf-8",
        check=True,
        shell=True,
        cwd=src.parent,
    )


@contextmanager
def using_defaults(defaults: dict[str, Any]) -> Generator[Path]:
    PATH_BUILD.mkdir(parents=True, exist_ok=True)
    try:
        with NamedTemporaryFile(
            "w", encoding="utf-8", prefix="build.", suffix=".yml", dir=PATH_BUILD, delete=False
        ) as f:
            yaml.dump(defaults, f)
        path = Path(f.name)
        yield path
    finally:
        with suppress(Exception):
            path.unlink(missing_ok=True)  # pyright: ignore[reportPossiblyUnboundVariable]


def pandoc_output_details(stdout: str, stderr: str, *extras: str) -> str:
    extra = "\n".join(chain(map(str.strip, extras), (stdout.strip(), stderr.strip()))).strip()
    if extra:
        extra = "\n    ".join(chain(":", extra.splitlines()))
    return extra


def pandoc_output(inp: Path, out: Path) -> str:
    return f"pandoc {inp} -> {out}"


@from_namespace
def main_from_markdown(input: Path, type: str, **_) -> None:  # noqa: A002, ANN003
    outfile = input.with_suffix(f".{type}")
    print(pandoc_output(input, outfile), end="", file=sys.stderr)

    try:
        fm = frontmatter(input.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        fm = {}
        buf = io.StringIO()
        traceback.print_exc(limit=1, file=buf, chain=False)

        print(
            ":\n    Unable to find frontmatter:\n         "
            + "\n        ".join(chain((str(e.__class__.__name__),), str(e).splitlines())),
            file=sys.stderr,
        )
    while True:
        try:
            with using_defaults(fm) as filepath:
                proc = pandoc(input, outfile, "--defaults", str(filepath))
            print(pandoc_output_details(proc.stdout, proc.stderr, yaml.dump(fm)), file=sys.stderr)
            break
        except subprocess.CalledProcessError as e:
            res: str = e.stderr
            if (idx := res.rfind("Unknown option")) == -1:
                print(
                    pandoc_output_details(e.stdout, e.stderr, yaml.dump(fm)),
                    file=sys.stderr,
                )
                raise
            line = res[idx : res.find("\n", idx)].strip()
            option = line.split("Unknown option")[1].strip().strip("'\"")
            fm.pop(option, None)


def cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()

    def as_path(path: str) -> Path:
        return Path(path).resolve()

    parser.set_defaults(py_main=main_from_markdown)
    parser.add_argument("input", type=as_path, help="Input markdown file")
    parser.add_argument("-t", "--type", type=str, default="pdf", help="Output file type (e.g., pdf, docx)")

    return parser


def main() -> None:
    args = cli().parse_args()
    try:
        args.py_main(args)
    except subprocess.CalledProcessError as _:
        sys.exit(1)


if __name__ == "__main__":
    main()

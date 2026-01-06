import argparse
import io
import re
import subprocess
import sys
import traceback
from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager, suppress
from itertools import chain
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import yaml

from .paths import PATH_BUILD


def from_namespace[**A, R](func: Callable[A, R]) -> Callable[[argparse.Namespace], R]:
    def decorator(args: argparse.Namespace) -> R:
        return func(**vars(args))  # pyright: ignore[reportCallIssue]

    return decorator


def frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    MARKER = "---"
    markdown = markdown.strip()
    if markdown.startswith(MARKER):
        mapping = markdown[len(MARKER) : markdown.find(MARKER, len(MARKER))]
        markdown = markdown[len(mapping) + 2 * len(MARKER) :].lstrip()
        return yaml.safe_load(mapping), markdown
    return {}, markdown


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


RE_MARKDOWN_HEADER = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def outline_markdown(markdown: str) -> Generator[tuple[int, str]]:
    for match in RE_MARKDOWN_HEADER.finditer(markdown):
        level = len(match.group(1))
        title = match.group(2).strip()
        yield (level, title)


def outline_as_tree(outline: Iterator[tuple[int, str]]) -> list[str | dict[str, Any]]:
    type Node = dict[str, Any]
    tree: Node = {}
    stack: list[tuple[int, Node]] = [(0, tree)]

    for level, title in outline:
        node: Node = {}
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent = stack[-1][1]
        parent[title] = node
        stack.append((level, node))

    def _flat_tree(node: Node) -> list[str | Node]:
        result: list[str | Node] = []
        for key, value in node.items():
            if not value:
                result.append(key)
            else:
                result.append({key: _flat_tree(value)})
        return result

    return _flat_tree(tree)


@from_namespace
def main_from_markdown(input: Path, type: str, show_outline: bool, **_) -> None:  # noqa: A002
    outfile = input.with_suffix(f".{type}")
    print(pandoc_output(input, outfile), end="", file=sys.stderr, flush=True)

    input_content = input.read_text(encoding="utf-8")

    try:
        fm, input_content = frontmatter(input_content)
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

            outline = outline_as_tree(outline_markdown(input_content)) if show_outline else {}
            print(
                pandoc_output_details(proc.stdout, proc.stderr, yaml.dump(fm), yaml.dump({"outline": outline})),
                file=sys.stderr,
            )
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
    parser.add_argument(
        "--no-outline", action="store_false", dest="show_outline", default=True, help="Show outline of the document"
    )

    return parser


def main() -> None:
    args = cli().parse_args()
    try:
        args.py_main(args)
    except subprocess.CalledProcessError as _:
        sys.exit(1)


if __name__ == "__main__":
    main()

from enum import Enum
from pathlib import Path
from typing import Generator, Dict, List

import tree_sitter_c as tsc
import tree_sitter_c_sharp as tscsharp
import tree_sitter_cpp as tscpp
import tree_sitter_javascript as tsjavascript
import tree_sitter_python as tspython
from tree_sitter import Language, Parser, Tree, Node
from tree_sitter_typescript import language_typescript as tstypescript


class Lang(Enum):
    PYTHON = "python"
    CPP = "cpp"
    C = "c"
    CSHARP = "c#"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"


ext_to_lang: Dict[str, Lang] = {
    "py": Lang.PYTHON,
    "h": Lang.CPP, "cc": Lang.CPP, "c": Lang.CPP, "cs": Lang.CSHARP,
    "cpp": Lang.CPP, "cxx": Lang.CPP, "hxx": Lang.CPP,
    "js": Lang.JAVASCRIPT, "mjs": Lang.JAVASCRIPT, "ts": Lang.TYPESCRIPT,
}

Languages: Dict[Lang, Language] = {
    Lang.PYTHON: Language(tspython.language()),
    Lang.CPP: Language(tscpp.language()),
    Lang.C: Language(tsc.language()),
    Lang.CSHARP: Language(tscsharp.language()),
    Lang.JAVASCRIPT: Language(tsjavascript.language()),
    Lang.TYPESCRIPT: Language(tstypescript()),
}

# Node type names that carry comment/docstring text, per language
COMMENT_NODE_TYPES: Dict[Lang, List[str]] = {
    Lang.PYTHON: ["comment", "string"],           
    Lang.CPP: ["comment", "raw_string_literal"],
    Lang.C: ["comment", "raw_string_literal"],
    Lang.CSHARP: ["comment"],
    Lang.JAVASCRIPT: ["comment"],
    Lang.TYPESCRIPT: ["comment", "jsdoc"],
}


def get_language(extension: str) -> Lang:
    return ext_to_lang[extension[1:]]


def read_file(file_path: str):
    path = Path(file_path)
    extension = path.suffix.lower()
    lang = get_language(extension)
    with open(file_path, "rb") as f:
        return f.read(), path.name, lang


def parse_code(code: bytes, lang: Lang) -> Tree:
    parser = Parser(Languages[lang])
    return parser.parse(code)


def _walk_comment_nodes(node: Node, target_types: List[str]) -> Generator[Node, None, None]:
    """Depth-first walk yielding nodes whose type is in target_types."""
    if node.type in target_types:
        yield node
    for child in node.children:
        yield from _walk_comment_nodes(child, target_types)


COMMENT_SYMBOLS = " *#'\"/–_="


def transform_text(text: str) -> str:
    return " ".join([part.lstrip(COMMENT_SYMBOLS) for part in text.split("\n") if part]).rstrip(
        COMMENT_SYMBOLS).removeprefix("\n ")


def extract_comments(lang: Lang, tree: Tree) -> Generator[str, None, None]:
    target_types = COMMENT_NODE_TYPES[lang]
    for node in _walk_comment_nodes(tree.root_node, target_types):
        raw = node.text.decode("utf-8", errors="replace")
        cleaned = transform_text(raw).strip()
        if cleaned:
            yield cleaned


def code_comments_iterator(file_path: str) -> Generator[str, None, None]:
    code, filename, lang = read_file(str(file_path))
    tree = parse_code(code, lang)
    yield from extract_comments(lang, tree)

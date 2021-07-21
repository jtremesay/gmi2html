#!/usr/bin/env python3
from argparse import ArgumentParser, FileType
from io import TextIOBase
from pathlib import Path
import re
import sys
from typing import Any, Dict, Generator, List, Optional, Sequence

header_regex = re.compile(r"(?P<tag>#+)\s+(?P<title>.*)")
element_regex = re.compile(r"\*\s+(?P<content>.*)")
link_regex = re.compile(r"=>\s*(?P<target>\S+)(\s+(?P<title>.+))?")


Token = Dict[str, Any]


def tokenize(gmi: TextIOBase) -> Generator[Token, None, None]:
    """Tokenize a gmetext stream

    Read the stream line by line and yield the token as soon as available

    """

    # The tokenizer use two state:
    # - "normal", where the stream is tokenized based on the language rules
    # - "quote", where the stream is stored verbatim

    # Store the content of a quote block when tokening it
    quote_token = None

    # Read the stream line by line until EOF
    for line in gmi:
        if quote_token is None:
            # Normal state

            # In this state, all pre and post whitespace area meaningless,
            # remove them
            line = line.strip()

            # Found a title
            if match := header_regex.match(line):
                group = match.groupdict()

                token = {
                    "kind": "header",
                    "level": len(group["tag"]),
                    "title": group["title"],
                }
                yield token

                continue

            # Found a list element
            if match := element_regex.match(line):
                group = match.groupdict()

                token = {"kind": "element", "content": group["content"]}
                yield token

                continue

            # Found a link
            if match := link_regex.match(line):
                group = match.groupdict()

                token = {
                    "kind": "link",
                    "target": group["target"],
                    "title": group["title"]
                    if group["title"] is not None
                    else "",
                }
                yield token

                continue

            # Found the begin of a quote
            if line.startswith("```"):
                quote_token = {"kind": "quote", "content": ""}
                continue

            # Just a line of text
            token = {"kind": "p", "content": line}
            yield token
        else:
            # Quote state

            # Found the end of a quote
            if line.startswith("```"):
                yield quote_token
                quote_token = None
                continue

            quote_token["content"] += line

    # Did we found the end quote token before EOF?
    if quote_token is not None:
        raise ValueError("Found a quote without end tag")


Node = Dict[str, Any]
RootNode = List[Node]


def build_ast(tokens: Token) -> RootNode:
    root = []
    links_node = None
    list_node = None
    quote_node = None
    for token in tokens:
        # Close node if needed
        if links_node is not None and token["kind"] != "link":
            root.append(links_node)
            links_node = None

        if list_node is not None and token["kind"] != "element":
            root.append(list_node)
            list_node = None

        if quote_node is not None and token["kind"] != "quote":
            root.append(quote_node)
            quote_node = None

        # Found a header token
        if token["kind"] == "header":
            node = {
                "kind": "header",
                "level": token["level"],
                "title": token["title"],
            }
            root.append(node)

            continue

        # Found a paragraph token
        if token["kind"] == "p":
            node = {"kind": "p", "content": token["content"]}
            root.append(node)

            continue

        # Found a link token
        if token["kind"] == "link":
            # Start the creation of a links node
            if links_node is None:
                links_node = {"kind": "links", "links": []}

            node = {
                "kind": "link",
                "target": token["target"],
                "title": token["title"],
            }
            links_node["links"].append(node)
            continue

        if token["kind"] == "element":
            # Start the creation of a list node
            if list_node is None:
                list_node = {"kind": "list", "elements": []}

            list_node["elements"].append(token["content"])
            continue

        if token["kind"] == "quote":
            # Start the creation of a quote node
            if quote_node is None:
                quote_node = {"kind": "quote", "content": []}

            quote_node["content"].append(token["content"])
            continue

        raise ValueError("Unhandled token of kind {}".format(token["kind"]))

    # Normally, only one can be not None
    # but i'm too lazy to write tests
    # TODO: add sanity tests
    if links_node is not None:
        root.append(links_node)

    if list_node is not None:
        root.append(list_node)

    if quote_node is not None:
        root.append(quote_node)

    return root


def write_html(ast: RootNode, out: Optional[TextIOBase] = sys.stdout) -> None:
    # Search the title of the page in the ast
    for node in ast:
        if node["kind"] == "header" and node["level"] == 1:
            title = node["title"]
            break
    else:
        title = "Page without title"

    out.write(
        """\
<!DOCTYPE html>
<html lang="en">
  <head>
   <meta charset="utf-8">
   <title>{}</title>\n""".format(title))

    out.write("""\
  <style type="text/css">
html {
	font-family: sans-serif;
	font-size:16px;
	line-height:1.6;
	color:#1E4147;
	background-color:#b3bccb;
}

body {
	max-width: 920px;
	margin: 0 auto;
	padding: 1rem 2rem;
}

h1,h2,h3{
	line-height:1.2;
}

h1 {
	text-align: center;
	margin-bottom: 1em;
}

blockquote {
	background-color: #eee;
	border-left: 3px solid #444;
	margin: 1rem -1rem 1rem calc(-1rem - 3px);
	padding: 1rem;
}

ul {
	margin-left: 0;
	padding: 0;
}

li {
	padding: 0;
}

li:not(:last-child) {
	margin-bottom: 0.5rem;
}

a {
	position: relative;
	color:#AA2E00;
}

a:visited {
	color: #802200;
}
   </style>
 </head>
 <body>
""")
    for node in ast:
        if node["kind"] == "header":
            out.write(
                "  <h{0}>{1}</h{0}>\n".format(node["level"], node["title"])
            )
            continue

        if node["kind"] == "p":
            out.write("  <p>{}</p>\n".format(node["content"]))
            continue

        if node["kind"] == "links":
            out.write("  <ul>\n")
            for link_node in node["links"]:
                out.write(
                    '    <li><a href="{}">{}</a></li>\n'.format(
                        link_node["target"], link_node["title"]
                    )
                )

            out.write("  </ul>\n")
            continue

        if node["kind"] == "list":
            out.write("  <ul>\n")

            for element in node["elements"]:
                out.write("    <li>{}</li>\n".format(element))

            out.write("  </ul>\n")
            continue

        if node["kind"] == "quote":
            out.write("  <pre>\n")
            for content in node["content"]:
                out.write(content + "\n")
            out.write("  </pre>\n")
            continue

        raise ValueError("Unhandled node of kind {}".format(node["kind"]))

    out.write(
        """\
 </body>
</html>
"""
    )


def gmi2html(gmi: TextIOBase, out: Optional[TextIOBase] = sys.stdout) -> None:
    tokens = tokenize(gmi)
    ast = build_ast(tokens)
    write_html(ast, out=out)


def cmd_convert(args):
    gmi2html(args.gmi_file, args.output)


def cmd_inetd(args):
    root_dir = args.root_dir
    
    with open("/dev/stdin") as f:
        request = f.readline().strip()

    try:
        resource = request.split()[1]
    except IndexError:
        return

    if not resource:
        return

    if resource.startswith("/"):
        resource = resource[1:]

    resource_path = root_dir / resource
    if not resource_path.suffix == ".gmi" or not resource_path.is_file():
        return

    
    with open("/dev/stdout", "w") as out:
        out.write("HTTP/1.0 200 OK\r\n")
        out.write("Content-Type: text/html; charset=utf-8")
        out.write("\r\n\r\n")

        with resource_path.open() as f:
            gmi2html(f, out)


def main(args: Optional[Sequence[str]] = None):
    arg_parser = ArgumentParser()

    subparsers = arg_parser.add_subparsers()

    convert_parser = subparsers.add_parser("convert")
    convert_parser.add_argument(
        "-o", "--output", type=FileType("w"), default="/dev/stdout"
    )
    convert_parser.add_argument("gmi_file", type=FileType("r"))
    convert_parser.set_defaults(func=cmd_convert)

    inetd_parser = subparsers.add_parser("inetd")
    inetd_parser.add_argument("root_dir", type=Path)
    inetd_parser.set_defaults(func=cmd_inetd)

    parsed_args = arg_parser.parse_args(args)
    try:
        func = parsed_args.func
    except AttributeError:
        print("no command specified")
        return

    func(parsed_args)


if __name__ == "__main__":
    main()

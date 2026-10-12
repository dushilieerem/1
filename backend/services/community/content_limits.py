"""Count rich-text content without markup or embedded image data."""
import re
from html.parser import HTMLParser


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "template"}:
            self.hidden_depth = max(0, self.hidden_depth - 1)

    def handle_data(self, data):
        if not self.hidden_depth:
            self.parts.append(data)


def post_body_text(value: str) -> str:
    value = value.strip()
    if not value.startswith("<") or not re.search(r"</[a-z][\w-]*>", value, re.I):
        return value
    parser = _TextParser()
    parser.feed(value)
    parser.close()
    return "".join(parser.parts).strip()

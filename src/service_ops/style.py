from __future__ import annotations

import os
import sys


class Style:
    def __init__(self) -> None:
        self.enabled = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

    def c(self, code: str, text: str) -> str:
        if not self.enabled:
            return text
        return f"\033[{code}m{text}\033[0m"

    def title(self, text: str) -> str:
        return self.c("1;36", text)

    def ok(self, text: str) -> str:
        return self.c("32", text)

    def warn(self, text: str) -> str:
        return self.c("33", text)

    def bad(self, text: str) -> str:
        return self.c("31", text)

    def dim(self, text: str) -> str:
        return self.c("2", text)


S = Style()

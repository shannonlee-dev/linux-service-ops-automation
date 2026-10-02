from __future__ import annotations

import sys

from .menu import menu
from .parser import build_parser, dispatch


def main() -> int:
    try:
        parser = build_parser()
        if len(sys.argv) == 1:
            menu()
            return 0
        args = parser.parse_args()
        return dispatch(args)
    except KeyboardInterrupt:
        print("\n중단했습니다.")
        return 130

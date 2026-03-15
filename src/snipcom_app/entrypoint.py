from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    launcher = Path(str(sys.argv[0] if sys.argv else "")).name.strip().casefold()
    if not args:
        if launcher == "scm":
            from .cli.cli import main as cli_main

            return int(cli_main([]))
        from .app import main as gui_main

        return int(gui_main())
    if args[0] in {"gui", "--gui", "--tutorial"}:
        from .app import main as gui_main

        return int(gui_main())

    from .cli.cli import main as cli_main

    return int(cli_main(args))

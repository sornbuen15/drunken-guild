#!/usr/bin/env python3
"""Truncate stdin to a number of *characters*, independently of the locale.

DG-280. Both installers used ``cut -c1-N``. ``cut -c`` counts bytes under
``LC_ALL=C`` and characters under a UTF-8 locale, and every description in this
repository carries em-dashes at three bytes each — so ``INDEX.md``, which is
generated *and* committed, came out differently depending on the shell that ran
the install. One operator's install dirtied 13 lines; the next regeneration
reverted all 13. Both are "the generator's output", which is the worst shape a
tracked artefact can have.

Byte truncation could also split a multibyte character. The committed file
stayed valid UTF-8 by where the boundary happened to fall, not by construction.

Bytes in and bytes out, decoded and encoded as UTF-8 explicitly: Python's own
stdin encoding follows the locale too, so reading ``sys.stdin`` directly would
reintroduce the bug this script exists to remove.
"""

import sys


def truncate(text: str, width: int) -> str:
    """The first *width* characters, without whatever whitespace ends them.

    The `rstrip` is not cosmetic. The awk that folds a multi-line YAML
    description joins it with `printf "%s "`, so the description ends in a
    space, and truncating mid-sentence lands on one often enough. Trailing
    whitespace is what `pre-commit` rewrites — and a generator whose output the
    commit hook edits can never produce the file that is in git, which is the
    same class of defect as the locale dependency above.
    """
    return text[:width].rstrip()


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <width>", file=sys.stderr)
        return 2
    try:
        width = int(sys.argv[1])
    except ValueError:
        print(f"{sys.argv[0]}: width must be an integer", file=sys.stderr)
        return 2

    # `errors="replace"` rather than strict: this runs inside an installer, and
    # a description with one bad byte should produce a slightly wrong line
    # rather than abort the install with a traceback.
    text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    sys.stdout.buffer.write(truncate(text.rstrip("\n"), width).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import argparse
from pathlib import Path
import zipfile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, required=True)
    args = parser.parse_args()
    wheels = sorted(args.dist.glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit("expected exactly one plugin wheel")
    with zipfile.ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())
    if "dar_external_adapter.json" not in names:
        raise SystemExit("plugin manifest is missing from wheel")
    if not any(
        name.endswith("dar_chrome_external_adapter/__init__.py") for name in names
    ):
        raise SystemExit("plugin factory module is missing from wheel")
    print(wheels[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

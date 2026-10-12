"""Strict build-only CLI; the plan module need not import the web application."""

import argparse
from ._shared import import_object


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build an application asset plan strictly"
    )
    parser.add_argument("plan", help="module:attribute reference to an AssetPlan")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    import_object(args.plan).ensure_built(strict=True, force=args.force)


if __name__ == "__main__":
    main()

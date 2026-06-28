"""CLI: `uv run badminton <discover|build|export|serve>`."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(prog="badminton", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_disc = sub.add_parser("discover", help="snowball the friend group into players.csv")
    p_disc.add_argument("--depth", type=int, default=2, help="match-graph hops to walk")

    sub.add_parser("build", help="fetch confirmed players -> matches.csv, xlsx, explorer")
    sub.add_parser("export", help="rebuild web/data.json from the source workbook")

    p_serve = sub.add_parser("serve", help="serve the static explorer at http://localhost:PORT")
    p_serve.add_argument("--port", type=int, default=8000)

    p_server = sub.add_parser(
        "server", help="run the full app (explorer + upload/nickname API) for deployment"
    )
    p_server.add_argument("--port", type=int, default=8000)
    p_server.add_argument("--host", default="0.0.0.0")

    p_upc = sub.add_parser("upcoming", help="scrape upcoming draws/schedule -> web/upcoming.json")
    p_upc.add_argument("--watch", action="store_true", help="loop, self-pacing the refresh")

    sub.add_parser("identity-seed", help="build people.csv + person_aliases.csv from players.csv")

    args = parser.parse_args()

    if args.command == "discover":
        from .discover import discover

        discover(max_depth=args.depth)

    elif args.command == "build":
        from .build import build
        from .export import export_json, roster_from_names
        from .fetch import fetch_all, load_players

        players = load_players()
        matches = fetch_all()
        build(matches, players)
        roster = [{"nickname": p["nickname"], "full_name": p["full_name"]} for p in players]
        # Fall back to nickname tokens so single-name friends still match.
        export_json(matches, roster or roster_from_names([]), source="tournamentsoftware")

    elif args.command == "export":
        from .export import export_from_excel

        export_from_excel()

    elif args.command == "serve":
        from .serve import serve

        serve(args.port)

    elif args.command == "server":
        from .server import run

        run(host=args.host, port=args.port)

    elif args.command == "upcoming":
        from .upcoming_build import run_upcoming

        if args.watch:
            from .upcoming_schedule import watch

            watch(run_upcoming)
        else:
            run_upcoming()

    elif args.command == "identity-seed":
        from .identity_seed import seed_identity

        n_people, n_aliases = seed_identity()
        print(f"Seeded {n_people} people, {n_aliases} aliases. "
              "Review data/people.csv + data/person_aliases.csv, then commit to the data/ repo.")


if __name__ == "__main__":
    main()

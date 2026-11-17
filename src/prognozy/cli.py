"""Polecenie ``prognozy``.

Przykłady:
    prognozy check                     # sprawdza konfigurację, nic nie wysyła
    prognozy run --mode test           # pytania testowe (bot-testing-area), próba
    prognozy run --mode tournament --publish
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from prognozy.config import Settings, missing_requirements
from prognozy.logs import setup_logging

logger = logging.getLogger("prognozy")

TEST_TOURNAMENT = "bot-testing-area"


def tournaments_for_mode(mode: str) -> list[int | str]:
    from forecasting_tools import MetaculusClient

    # Na nowy sezon można podać ID turnieju bez czekania na aktualizację biblioteki.
    main = os.getenv("PROGNOZY_TOURNAMENT") or MetaculusClient.CURRENT_AI_COMPETITION_ID
    minibench = os.getenv("PROGNOZY_MINIBENCH") or MetaculusClient.CURRENT_MINIBENCH_ID
    return {
        "tournament": [main, minibench],
        "aib": [main],
        "minibench": [minibench],
        "test": [TEST_TOURNAMENT],
    }[mode]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prognozy", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="sprawdź konfigurację (bez sieci)")
    run = sub.add_parser("run", help="jedno przejście bota")
    run.add_argument("--mode", choices=["tournament", "aib", "minibench", "test"],
                     default="tournament")
    group = run.add_mutually_exclusive_group()
    group.add_argument("--publish", action="store_true", default=None,
                       help="wysyłaj prognozy (nadpisuje PROGNOZY_PUBLISH)")
    group.add_argument("--dry-run", action="store_true",
                       help="nic nie wysyłaj, tylko pokaż co by poszło")
    return parser


def _cmd_check(settings: Settings) -> int:
    problems = missing_requirements()
    from prognozy.research import default_sources

    sources = [s.name for s in default_sources(settings.search_models)]
    print(f"Wysyłanie prognoz: {'TAK' if settings.publish else 'NIE (próba)'}")
    print(f"Katalog stanu: {settings.state_dir}")
    print(f"Prognoz na pytanie: {settings.predictions_per_question}")
    print(f"Źródła informacji: {', '.join(sources) if sources else 'BRAK'}")
    if not sources:
        problems.append("Brak źródeł informacji: ustaw ASKNEWS_* lub OPENROUTER_API_KEY.")
    for p in problems:
        print(f"BŁĄD: {p}")
    print("OK" if not problems else "Konfiguracja niekompletna.")
    return 0 if not problems else 1


def _cmd_run(settings: Settings, mode: str, publish: bool) -> int:
    problems = missing_requirements()
    if problems:
        for p in problems:
            logger.error(p)
        return 1

    from forecasting_tools import MetaculusClient

    from prognozy.bot import PrognozyBot
    from prognozy.ledger import Ledger
    from prognozy.research import Researcher, default_sources
    from prognozy.runner import run_once

    researcher = Researcher(default_sources(settings.search_models), settings.min_research_chars)
    if not researcher.source_names:
        logger.error("Brak źródeł informacji. Bot nie będzie prognozował na ślepo.")
        return 1

    client = MetaculusClient()
    bot = PrognozyBot(
        researcher=researcher,
        research_reports_per_question=1,
        predictions_per_research_report=settings.predictions_per_question,
        publish_reports_to_metaculus=False,  # wysyła Publisher, po kontroli
        skip_previously_forecasted_questions=False,  # filtruje runner
        enable_summarize_research=False,
        extra_metadata_in_explanation=True,
        llms=PrognozyBot.build_llms(
            settings.model_default, settings.model_parser, settings.model_summarizer
        ),
        metaculus_client=client,
    )
    ledger_name = "rejestr-test.sqlite" if mode == "test" else "rejestr.sqlite"
    ledger = Ledger(settings.state_dir / ledger_name)
    logger.info("Start: tryb=%s, wysyłanie=%s, źródła=%s", mode, publish, researcher.source_names)
    summary = asyncio.run(
        run_once(
            bot=bot,
            client=client,
            ledger=ledger,
            tournaments=tournaments_for_mode(mode),
            dry_run=not publish,
            # Na pytaniach testowych prognozujemy ponownie, ale rejestr testowy i tak blokuje duble.
            skip_forecasted=mode != "test",
        )
    )
    # Pojedyncze pominięte pytania to nie awaria usługi; awarią jest tylko błąd pobierania.
    fetch_failed = any("pobieranie pytań" in f for f in summary.failed)
    return 1 if fetch_failed else 0


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = _build_parser().parse_args(argv)
    settings = Settings.from_env()
    if args.command == "check":
        return _cmd_check(settings)
    publish = settings.publish
    if args.publish:
        publish = True
    if args.dry_run:
        publish = False
    return _cmd_run(settings, args.mode, publish)


if __name__ == "__main__":
    sys.exit(main())

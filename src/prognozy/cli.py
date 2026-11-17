"""Polecenie ``prognozy``.

Przykłady:
    prognozy check                     # sprawdza konfigurację, nic nie wysyła
    prognozy run --mode test           # pytania testowe (bot-testing-area), próba
    prognozy run --mode tournament --publish
    prognozy porownaj --modele openrouter/openai/gpt-5.4,openrouter/anthropic/claude-opus-5.5
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
    cmp_ = sub.add_parser(
        "porownaj",
        help="porównaj modele na otwartych pytaniach spoza turniejów (nic nie wysyła)",
    )
    cmp_.add_argument("--modele", required=True,
                      help="warianty po przecinku; wariant z '+' to zespół, np. a+b")
    cmp_.add_argument("--pytania", type=int, default=30, help="liczba pytań (domyślnie 30)")
    return parser


def _default_parser_model() -> str | None:
    """Tani model biblioteki (np. Claude Haiku) do układania zapytań o rynki."""
    from forecasting_tools import ForecastBot, GeneralLlm

    parser = ForecastBot._llm_config_defaults().get("parser")
    return GeneralLlm.to_model_name(parser) if parser else None


def _make_researcher(settings: Settings, cache: bool = False):
    from prognozy.research import Researcher, default_sources

    sources = default_sources(
        settings.search_models,
        markets=settings.markets,
        market_query_model=settings.model_parser or _default_parser_model(),
    )
    return Researcher(sources, settings.min_research_chars, cache=cache)


def _make_bot(settings: Settings, researcher, client, forecast_models: tuple[str, ...]):
    from prognozy import throttle
    from prognozy.bot import PrognozyBot

    throttle.configure(settings.llm_rpm)
    return PrognozyBot(
        researcher=researcher,
        forecast_models=forecast_models,
        parallel_questions=settings.parallel_questions,
        prompt_cache=settings.prompt_cache,
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


def _cmd_check(settings: Settings) -> int:
    problems = missing_requirements()
    researcher = _make_researcher(settings)
    print(f"Wysyłanie prognoz: {'TAK' if settings.publish else 'NIE (próba)'}")
    print(f"Katalog stanu: {settings.state_dir}")
    print(f"Prognoz na pytanie: {settings.predictions_per_question}")
    print(f"Modele prognozy: {', '.join(settings.forecast_models) or settings.model_default or 'domyślny z biblioteki'}")
    print(f"Źródła informacji: {', '.join(researcher.source_names) or 'BRAK'}")
    print(f"Powiadomienia (healthcheck): {'TAK' if settings.healthcheck_url else 'NIE'}")
    print(f"Dzienny limit wydatków: {settings.daily_budget_usd or 'brak'}")
    if not researcher.has_primary_source:
        problems.append("Brak głównego źródła informacji: ustaw ASKNEWS_* lub OPENROUTER_API_KEY.")
    for p in problems:
        print(f"BŁĄD: {p}")
    print("OK" if not problems else "Konfiguracja niekompletna.")
    return 0 if not problems else 1


def _cmd_run(settings: Settings, mode: str, publish: bool) -> int:
    from prognozy.ops import DailyBudget, Healthcheck, NotABotAccount, check_bot_account

    health = Healthcheck(settings.healthcheck_url)
    health.start()
    problems = missing_requirements()
    researcher = _make_researcher(settings)
    if not researcher.has_primary_source:
        problems.append("Brak źródeł informacji. Bot nie będzie prognozował na ślepo.")
    if problems:
        for p in problems:
            logger.error(p)
        health.fail("\n".join(problems))
        return 1

    try:
        bot_name = check_bot_account(os.getenv("METACULUS_TOKEN"))
    except NotABotAccount as exc:
        logger.error("%s", exc)
        health.fail(str(exc))
        return 1
    if bot_name:
        logger.info("Konto bota: %s", bot_name)

    from forecasting_tools import MetaculusClient

    from prognozy.ledger import Ledger
    from prognozy.runner import run_once

    client = MetaculusClient()
    bot = _make_bot(settings, researcher, client, settings.forecast_models)
    ledger_name = "rejestr-test.sqlite" if mode == "test" else "rejestr.sqlite"
    ledger = Ledger(settings.state_dir / ledger_name)
    logger.info("Start: tryb=%s, wysyłanie=%s, źródła=%s", mode, publish, researcher.source_names)
    try:
        summary = asyncio.run(
            run_once(
                bot=bot,
                client=client,
                ledger=ledger,
                tournaments=tournaments_for_mode(mode),
                dry_run=not publish,
                # Na pytaniach testowych prognozujemy ponownie; rejestr testowy i tak blokuje duble.
                skip_forecasted=mode != "test",
                budget=DailyBudget(settings.daily_budget_usd),
                batch_size=settings.batch_size,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Przejście przerwane błędem.")
        health.fail(f"{type(exc).__name__}: {exc}")
        return 1
    # Pojedyncze pominięte pytania to nie awaria usługi; awaria to brak dostępu do pytań.
    if summary.fetch_failed:
        health.fail(summary.report())
        return 1
    health.success(summary.report())
    return 0


def _cmd_compare(settings: Settings, variants_arg: str, n: int) -> int:
    problems = missing_requirements()
    researcher = _make_researcher(settings, cache=True)
    if problems or not researcher.has_primary_source:
        for p in problems or ["Brak źródeł informacji."]:
            logger.error(p)
        return 1

    from forecasting_tools import MetaculusClient

    from prognozy.compare import exclude_tournament_questions, run_comparison, save_rows, summarize

    client = MetaculusClient()
    # Pobieramy więcej, bo część odpadnie (pytania turniejowe / bez CP).
    questions = client.get_benchmark_questions(n * 2, error_if_question_target_missed=False)
    forbidden = tournaments_for_mode("tournament") + [TEST_TOURNAMENT]
    questions = exclude_tournament_questions(questions, forbidden)[:n]
    if not questions:
        logger.error("Brak pytań do porównania.")
        return 1
    variants = {
        v: _make_bot(settings, researcher, client, tuple(v.split("+")))
        for v in (x.strip() for x in variants_arg.split(",")) if v
    }
    logger.info("Porównanie: %d pytań, warianty: %s", len(questions), list(variants))
    rows = asyncio.run(run_comparison(questions, variants))
    path = save_rows(rows, settings.state_dir / "porownania")
    print(summarize(rows))
    print(f"\nSzczegóły: {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = _build_parser().parse_args(argv)
    settings = Settings.from_env()
    if args.command == "check":
        return _cmd_check(settings)
    if args.command == "porownaj":
        return _cmd_compare(settings, args.modele, args.pytania)
    publish = settings.publish
    if args.publish:
        publish = True
    if args.dry_run:
        publish = False
    return _cmd_run(settings, args.mode, publish)


if __name__ == "__main__":
    sys.exit(main())

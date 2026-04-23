from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

from utils.logger import setup_logger, get_logger
from utils.config_loader import load_config, cron_kwargs
from collectors import g2b_api, kapt_api, alio_crawler, g2b_crawler, d2b_api, kwater_api
from db import database
from filters import keyword_filter
from notifiers import email_notifier, slack_notifier


def _init(config_path: Path):
    config = load_config(config_path)
    log_cfg = config.get("logging") or {}
    log_file = log_cfg.get("file")
    if log_file and not Path(log_file).is_absolute():
        log_file = str(ROOT / log_file)
    setup_logger(
        level=log_cfg.get("level", "INFO"),
        log_file=log_file,
        max_bytes=int(log_cfg.get("max_bytes", 10 * 1024 * 1024)),
        backup_count=int(log_cfg.get("backup_count", 5)),
    )
    return config


def _db_path(config: dict) -> Path:
    p = Path(config.get("database", {}).get("path") or "data/bids.sqlite")
    return p if p.is_absolute() else ROOT / p


def run_collect(config: dict) -> int:
    logger = get_logger()
    sources = (config.get("collection", {}).get("sources") or {})
    sleep_seconds = float(config.get("collection", {}).get("request_sleep_seconds", 1.5))
    page_size = int(config.get("collection", {}).get("page_size", 100))
    lookback_days = int(config.get("collection", {}).get("lookback_days", 1))

    db_path = _db_path(config)
    database.init_db(db_path)

    total_collected = 0

    if sources.get("g2b_api"):
        key = os.environ.get("G2B_SERVICE_KEY")
        if not key:
            logger.error("G2B_SERVICE_KEY missing in env — skipping g2b_api")
        else:
            try:
                rows = g2b_api.collect_all(
                    service_key=key,
                    page_size=page_size,
                    sleep_seconds=sleep_seconds,
                    lookback_days=lookback_days,
                )
                database.upsert_bids(db_path, rows)
                total_collected += len(rows)
            except Exception:
                logger.exception("g2b_api collection crashed")

    if sources.get("kapt_api"):
        key = os.environ.get("KAPT_SERVICE_KEY")
        if not key:
            logger.warning("KAPT_SERVICE_KEY missing in env — skipping kapt_api")
        else:
            try:
                kapt_cfg = (config.get("collection", {}).get("kapt") or {})
                rows = kapt_api.collect(
                    service_key=key,
                    base_url=kapt_cfg.get("base_url") or kapt_api.DEFAULT_BASE_URL,
                    operation=kapt_cfg.get("operation") or kapt_api.DEFAULT_OPERATION,
                    page_size=page_size,
                    sleep_seconds=sleep_seconds,
                    lookback_days=lookback_days,
                )
                database.upsert_bids(db_path, rows)
                total_collected += len(rows)
            except Exception:
                logger.exception("kapt_api collection crashed")

    if sources.get("alio"):
        try:
            alio_cfg = (config.get("collection", {}).get("alio") or {})
            rows = alio_crawler.collect(
                word=alio_cfg.get("keyword", ""),
                max_pages=int(alio_cfg.get("max_pages", 10)),
                sleep_seconds=sleep_seconds,
                lookback_days=lookback_days,
            )
            database.upsert_bids(db_path, rows)
            total_collected += len(rows)
        except Exception:
            logger.exception("alio collection crashed")

    if sources.get("g2b_crawler"):
        # Deprecated stub — legacy endpoint unavailable since site redesign.
        g2b_crawler.collect()

    if sources.get("d2b_api"):
        key = os.environ.get("G2B_SERVICE_KEY") or os.environ.get("D2B_SERVICE_KEY")
        if not key:
            logger.warning("D2B/G2B_SERVICE_KEY missing — skipping d2b_api")
        else:
            try:
                rows = d2b_api.collect_all(
                    service_key=key,
                    page_size=page_size,
                    sleep_seconds=sleep_seconds,
                    lookback_days=lookback_days,
                )
                database.upsert_bids(db_path, rows)
                total_collected += len(rows)
            except Exception:
                logger.exception("d2b_api collection crashed")

    if sources.get("kwater_api"):
        key = os.environ.get("G2B_SERVICE_KEY") or os.environ.get("KWATER_SERVICE_KEY")
        kwater_cfg = (config.get("collection", {}).get("kwater") or {})
        if not key or not kwater_cfg.get("base_url"):
            logger.warning("kwater: key or base_url missing — skipping kwater_api")
        else:
            try:
                rows = kwater_api.collect(
                    service_key=key,
                    base_url=kwater_cfg.get("base_url", ""),
                    type_param=kwater_cfg.get("type_param", "_type"),
                    page_size=page_size,
                    sleep_seconds=sleep_seconds,
                    lookback_days=lookback_days,
                )
                database.upsert_bids(db_path, rows)
                total_collected += len(rows)
            except Exception:
                logger.exception("kwater_api collection crashed")

    logger.info("collection complete: %d rows total", total_collected)
    return total_collected


def run_notify(config: dict, dry_run: bool = False) -> int:
    logger = get_logger()
    db_path = _db_path(config)
    notifier_cfg = config.get("notifier") or {}
    channels = notifier_cfg.get("channels") or []

    rows = database.get_unnotified(db_path)
    filtered = keyword_filter.apply_filters(rows, config.get("filters") or {})
    logger.info("notify: %d unnotified -> %d after filter", len(rows), len(filtered))

    if not filtered:
        return 0

    if dry_run:
        logger.info("[DRY-RUN] would send to channels=%s, %d rows", channels, len(filtered))
        html = email_notifier.build_html(filtered)
        blocks = slack_notifier.build_blocks(filtered)
        logger.info("[DRY-RUN] email HTML: %d chars", len(html))
        logger.info("[DRY-RUN] slack blocks: %d", len(blocks))
        for r in filtered[:10]:
            logger.info("  - [%s] %s | %s | %s",
                        r.get("bid_type"), r.get("bid_no"),
                        (r.get("title") or "")[:60], r.get("org_name"))
        if len(filtered) > 10:
            logger.info("  ... and %d more", len(filtered) - 10)
        return len(filtered)

    any_sent = False
    if "email" in channels:
        ok = email_notifier.send_email(filtered, notifier_cfg)
        any_sent = any_sent or ok
    if "slack" in channels:
        ok = slack_notifier.send_slack(filtered, notifier_cfg)
        any_sent = any_sent or ok

    if any_sent:
        database.mark_notified(db_path, [r["id"] for r in filtered])
    return len(filtered) if any_sent else 0


def run_once(config: dict, dry_run: bool = False) -> None:
    run_collect(config)
    run_notify(config, dry_run=dry_run)


def run_scheduler(config: dict) -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler

    logger = get_logger()
    sched_cfg = config.get("schedule") or {}
    tz = sched_cfg.get("timezone", "Asia/Seoul")

    sched = BlockingScheduler(timezone=tz)
    sched.add_job(
        lambda: run_collect(config),
        "cron",
        **cron_kwargs(sched_cfg.get("collect_cron", "0 8 * * *")),
        id="collect",
        max_instances=1,
        coalesce=True,
    )
    sched.add_job(
        lambda: run_notify(config),
        "cron",
        **cron_kwargs(sched_cfg.get("notify_cron", "30 8 * * *")),
        id="notify",
        max_instances=1,
        coalesce=True,
    )
    logger.info("scheduler started (tz=%s)", tz)
    for job in sched.get_jobs():
        logger.info("  job=%s trigger=%s", job.id, job.trigger)
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("scheduler stopped")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="대한민국 입찰정보 수집 툴")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--run-once", action="store_true",
                        help="스케줄러 없이 수집+알림 1회 실행")
    parser.add_argument("--collect-only", action="store_true", help="수집만 1회")
    parser.add_argument("--notify-only", action="store_true", help="알림만 1회")
    parser.add_argument("--dry-run", action="store_true",
                        help="알림 전송/플래그 갱신 없이 payload만 로그 출력")
    args = parser.parse_args(argv)

    config = _init(Path(args.config))

    if args.collect_only:
        run_collect(config)
    elif args.notify_only:
        run_notify(config, dry_run=args.dry_run)
    elif args.run_once:
        run_once(config, dry_run=args.dry_run)
    else:
        run_scheduler(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())

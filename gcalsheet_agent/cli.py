from __future__ import annotations

import os
import sys
import click
import datetime as dt

from .config import load_config, save_config, AppConfig, ensure_state_dir, DEFAULT_CONFIG_PATH
from .logging_conf import configure_logging
from .google_clients import authenticate_google
from .sync_engine import SyncEngine


@click.group()
@click.option("--config", "config_path", default=DEFAULT_CONFIG_PATH, help="Path to config.json")
@click.option("--verbose", is_flag=True, help="Verbose logging")
@click.pass_context
def cli(ctx: click.Context, config_path: str, verbose: bool):
    configure_logging(verbose)
    cfg = load_config(config_path)
    ensure_state_dir(os.path.dirname(config_path))
    ctx.obj = {"cfg": cfg, "config_path": config_path}


@cli.command()
@click.pass_context
def init(ctx: click.Context):
    cfg: AppConfig = ctx.obj["cfg"]
    save_config(cfg, ctx.obj["config_path"])
    click.echo(f"Initialized config at {ctx.obj['config_path']}")


@cli.command("auth-google")
@click.pass_context
def auth_google(ctx: click.Context):
    cfg: AppConfig = ctx.obj["cfg"]
    click.echo("Starting Google OAuth flow; a browser will open...")
    authenticate_google(cfg)
    save_config(cfg, ctx.obj["config_path"])
    click.echo("Google authentication successful.")


@cli.command()
@click.option("--now", default=None, help="Date for week (YYYY-MM-DD)")
@click.option("--apply-updates", is_flag=True, help="Apply 2-way updates from sheet to calendar")
@click.pass_context
def run(ctx: click.Context, now: str | None, apply_updates: bool):
    cfg: AppConfig = ctx.obj["cfg"]
    _cal, _sheets, _drive = authenticate_google(cfg)
    # Detect timezone once
    from .calendar_manager import CalendarManager

    cal_mgr = CalendarManager(cfg, _cal, tz="UTC")
    tz = cal_mgr.get_calendar_timezone()

    engine = SyncEngine(cfg, _cal, _sheets, _drive, tz)

    date_obj = dt.datetime.strptime(now, "%Y-%m-%d").date() if now else None
    sheet_info, events = engine.sync_week(now=date_obj)

    click.echo(f"Synced {len(events)} events to sheet '{sheet_info.title}'.")

    if apply_updates and cfg.sync.two_way:
        row_updates = engine.sheet_to_calendar_updates(sheet_info)
        applied = engine.apply_updates_to_calendar(sheet_info, row_updates)
        click.echo(f"Applied {len(applied)} updates from sheet to calendar.")


@cli.command("print-config")
@click.pass_context
def print_config(ctx: click.Context):
    import json
    from dataclasses import asdict

    cfg: AppConfig = ctx.obj["cfg"]
    click.echo(json.dumps(asdict(cfg), indent=2))


def main():
    cli(prog_name="gcalsheet-agent")


if __name__ == "__main__":
    main()

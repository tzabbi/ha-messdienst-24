#!/usr/bin/env python3
"""Testet den Client der Integration ohne Home Assistant (benötigt aiohttp)."""

import asyncio
import configparser
import importlib.util
import sys
import types
from pathlib import Path

import aiohttp

HERE = Path(__file__).resolve().parent
PKG_DIR = HERE.parent / "custom_components" / "messdienst24"

# Load api/parsing/const as a package without importing __init__.py (needs HA).
pkg = types.ModuleType("md24")
pkg.__path__ = [str(PKG_DIR)]
sys.modules["md24"] = pkg
for name in ("const", "parsing", "api"):
    spec = importlib.util.spec_from_file_location(
        f"md24.{name}", PKG_DIR / f"{name}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"md24.{name}"] = mod
    spec.loader.exec_module(mod)
api = sys.modules["md24.api"]


async def main(password_override: str | None) -> None:
    cfg = configparser.ConfigParser()
    cfg.read(HERE / "credentials.ini", encoding="utf-8")
    sec = cfg["messdienst24"]
    async with aiohttp.ClientSession() as session:
        client = api.Messdienst24Client(
            session,
            sec["username"],
            password_override or sec["password"],
            sec.get("md", "ex"),
        )
        try:
            meters = await client.async_get_meters()
        except api.Messdienst24Error as err:
            print(f"{type(err).__name__}: {err}")
            return
        for m in meters:
            print(f"{m.label:<11} {m.number}  {m.latest.value:>10}  ({m.latest.date})")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))

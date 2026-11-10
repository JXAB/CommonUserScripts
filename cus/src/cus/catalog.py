"""Read-only JSON catalog. No dynamic shell evaluation, imports or remote code."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_catalog(name: str) -> dict:
    if name not in {"modules", "profiles"}:
        raise ValueError("Invalid catalog")
    with (ROOT / "data" / (name + ".json")).open(encoding="utf-8") as f:
        return json.load(f)


def modules() -> dict:
    return {x["id"]: x for x in load_catalog("modules")["modules"]}


def profiles() -> dict:
    return {x["id"]: x for x in load_catalog("profiles")["profiles"]}


def status(module: dict, host: dict) -> tuple[str, str]:
    detect = module.get("detect", [])
    if detect:
        import shutil
        found = [name for name in detect if shutil.which(name)]
        if len(found) == len(detect):
            return "detected", ",".join(found)
        if found:
            return "partial", ",".join(found)
    if module["kind"] == "builtin":
        return "ready", "built into manager"
    if module["kind"] == "planned":
        return "planned", "adapter not yet implemented"
    if not host.get("manager") or host["manager"] not in module.get("packages", {}):
        return "unsupported", "no verified adapter for this OS"
    return "available", "native package manager"


def package_command(module: dict, host: dict) -> list[str] | None:
    if module["kind"] != "package":
        return None
    mgr = host.get("manager")
    ids = module.get("packages", {}).get(mgr)
    if not ids:
        return None
    if mgr == "apt":
        return ["apt", "install", "-y", "--", *ids]
    if mgr == "dnf":
        return ["dnf", "install", "-y", "--", *ids]
    if mgr == "pacman":
        return ["pacman", "-S", "--needed", "--noconfirm", "--", *ids]
    if mgr == "brew":
        return ["brew", "install", *ids]
    if mgr == "winget":
        # All other winget recipes intentionally disabled in the starter.
        if len(ids) == 1:
            return ["winget", "install", "--id", ids[0], "--exact",
                    "--accept-package-agreements", "--accept-source-agreements"]
    return None


def plan_module(mid: str, host: dict) -> dict:
    """One module's plan: status, detail, commands, install readiness.

    Kept here (not in cli.py) so the CLI and the console share one source
    of truth. A plan is never a claim that anything was installed.
    """
    catalog = modules()
    if mid not in catalog:
        raise ValueError(f"Unknown module: {mid}")
    item = catalog[mid]
    state, reason = status(item, host)
    command = package_command(item, host)
    return {"id": mid, "name": item["name"], "kind": item["kind"],
            "status": state, "detail": reason, "commands": [command] if command else [],
            "install_ready": item["kind"] == "package" and command is not None}

#!/usr/bin/env python3
"""Instala o bridge do plugin no host sem remover comandos ou skills existentes."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import stat
import subprocess
import sys
import time
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_SOURCE = PLUGIN_ROOT / "bin" / "multiagent-bridge"
DEFAULT_BIN_DIR = Path("~/.local/bin").expanduser()
DEFAULT_BRIDGE_DIR = Path("~/.agents/cowork-bridge").expanduser()
DEFAULT_CONFIG = Path("~/.agents/cowork-bridge-config.json").expanduser()
DEFAULT_PRIVATE_STATE = Path("~/.agents/cowork-bridge-state").expanduser()
LAUNCHD_DIR = Path("~/Library/LaunchAgents").expanduser()
LAUNCHD_LABEL = "com.nicholasjacob.multiagent-cowork-bridge"


def write_atomic(path: Path, text: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    if mode is not None:
        tmp.chmod(mode)
    os.replace(tmp, path)


def install_wrapper(bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    target = bin_dir / "multiagent-bridge"
    home = Path.home().resolve()
    route_path = os.pathsep.join(
        dict.fromkeys(
            [
                "/opt/homebrew/bin",
                "/usr/local/bin",
                "/usr/bin",
                "/bin",
                "/usr/sbin",
                "/sbin",
                str(home / ".local" / "bin"),
            ]
        )
    )
    interpreter = Path(sys.executable).resolve()
    wrapper = f'''#!/bin/sh
set -eu
export MULTIAGENT_PLUGIN_ROOT="{PLUGIN_ROOT}"
export PATH="{route_path}"
exec "{interpreter}" "{PLUGIN_ROOT / 'scripts' / 'cowork_bridge.py'}" "$@"
'''
    write_atomic(target, wrapper, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
    return target


def launchd_plist(wrapper: Path, bridge_dir: Path, config: Path, private_state: Path) -> str:
    stdout = bridge_dir / "state" / "bridge.stdout.log"
    stderr = bridge_dir / "state" / "bridge.stderr.log"
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{LAUNCHD_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{wrapper}</string>
    <string>--bridge-dir</string><string>{bridge_dir}</string>
    <string>--config</string><string>{config}</string>
    <string>--private-state</string><string>{private_state}</string>
    <string>serve</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>{stdout}</string>
  <key>StandardErrorPath</key><string>{stderr}</string>
</dict>
</plist>
'''


def configure_launchd(wrapper: Path, bridge_dir: Path, config: Path, private_state: Path) -> Path:
    target = LAUNCHD_DIR / f"{LAUNCHD_LABEL}.plist"
    write_atomic(target, launchd_plist(wrapper, bridge_dir, config, private_state), 0o600)
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", domain, str(target)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    completed = None
    for delay in (0.1, 0.25, 0.5, 1.0):
        completed = subprocess.run(
            ["launchctl", "bootstrap", domain, str(target)],
            text=True, capture_output=True, check=False,
        )
        if completed.returncode == 0:
            break
        time.sleep(delay)
    if completed is None or completed.returncode != 0:
        message = (completed.stderr or completed.stdout).strip() if completed else ""
        raise RuntimeError(message or "launchctl bootstrap falhou")
    subprocess.run(["launchctl", "kickstart", "-k", f"{domain}/{LAUNCHD_LABEL}"], check=False)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin-dir", default=str(DEFAULT_BIN_DIR))
    parser.add_argument("--bridge-dir", default=str(DEFAULT_BRIDGE_DIR))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--private-state", default=str(DEFAULT_PRIVATE_STATE))
    parser.add_argument("--launchd", action="store_true", help="iniciar e manter o bridge no login do macOS")
    args = parser.parse_args()
    bin_dir = Path(args.bin_dir).expanduser().resolve()
    bridge_dir = Path(args.bridge_dir).expanduser().resolve()
    config = Path(args.config).expanduser().resolve()
    private_state = Path(args.private_state).expanduser().resolve()
    for name in ("inbox", "processing", "outbox", "failed", "state"):
        (bridge_dir / name).mkdir(parents=True, exist_ok=True)
        (bridge_dir / name).chmod(0o700)
    bridge_dir.chmod(0o700)
    private_state.mkdir(parents=True, exist_ok=True)
    private_state.chmod(0o700)
    if Path(args.config).expanduser().is_symlink():
        raise RuntimeError(f"configuração privada não pode ser symlink: {args.config}")
    if config.exists():
        try:
            existing = json.loads(config.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"configuração existente inválida: {config}: {exc}") from exc
        roots = existing.get("roots", {}) if isinstance(existing.get("roots"), dict) else {}
        secret = existing.get("bridge_secret") or secrets.token_hex(32)
    else:
        roots = {}
        secret = secrets.token_hex(32)
    write_atomic(
        config,
        json.dumps(
            {"config_version": 2, "bridge_secret": secret, "roots": roots},
            ensure_ascii=False, indent=2, sort_keys=True,
        ) + "\n",
        0o600,
    )
    wrapper = install_wrapper(bin_dir)
    plist = configure_launchd(wrapper, bridge_dir, config, private_state) if args.launchd else None
    print(f"bridge={wrapper}")
    print(f"queue={bridge_dir}")
    print(f"config={config}")
    print(f"private_state={private_state}")
    print(f"launchd={plist or 'not-configured'}")
    if str(bin_dir) not in os.environ.get("PATH", "").split(os.pathsep):
        print(f"warning={bin_dir} não está no PATH atual", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_FILE = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / ".bridge" / "bridge.md"
LOG_FILE = Path(sys.argv[2]) if len(sys.argv) > 2 else REPO_ROOT / ".bridge" / "monitor.log"
STATE_FILE = Path(sys.argv[3]) if len(sys.argv) > 3 else REPO_ROOT / ".bridge" / "codex-monitor.state.json"
POLL_INTERVAL = int(os.environ.get("BRIDGE_POLL_INTERVAL", "30"))
ASSIGNEES = {"codex", "shared"}


@dataclass
class Task:
    task_id: int
    assignee: str
    status: str
    requested_by: str
    updated_at: str
    summary: str
    details: list[str]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def log(message: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"[{now_iso()}] {message}\n")


def load_state() -> dict[str, int]:
    if not STATE_FILE.exists():
        return {"last_handled_task_id": 0}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"last_handled_task_id": 0}


def save_state(state: dict[str, int]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def extract_field(section: str, name: str) -> str:
    match = re.search(rf"^- {re.escape(name)}:\s*(.*)$", section, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def parse_task(text: str) -> Task | None:
    match = re.search(r"## Active Task\n(.*?)(?:\n## |\Z)", text, flags=re.DOTALL)
    if not match:
        return None

    active = match.group(1)
    details_match = re.search(r"^- Details:\n((?:  - .*\n?)*)", active, flags=re.MULTILINE)
    details_block = details_match.group(1) if details_match else ""
    details = [line[4:].strip() for line in details_block.splitlines() if line.startswith("  - ")]

    task_id_raw = extract_field(active, "Task ID")
    try:
        task_id = int(task_id_raw)
    except ValueError:
        return None

    return Task(
        task_id=task_id,
        assignee=extract_field(active, "Assignee").lower(),
        status=extract_field(active, "Status").lower(),
        requested_by=extract_field(active, "Requested By"),
        updated_at=extract_field(active, "Updated At"),
        summary=extract_field(active, "Summary"),
        details=details,
    )


def replace_once(text: str, pattern: str, replacement: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count == 0:
        raise RuntimeError(f"Pattern not found: {pattern}")
    return updated


def mutate_bridge(mutator: Callable[[str], str]) -> None:
    for _ in range(10):
        original = BRIDGE_FILE.read_text(encoding="utf-8")
        before_stat = BRIDGE_FILE.stat()
        updated = mutator(original)
        after_stat = BRIDGE_FILE.stat()
        if (
            before_stat.st_mtime_ns != after_stat.st_mtime_ns
            or before_stat.st_size != after_stat.st_size
        ):
            time.sleep(0.2)
            continue

        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(BRIDGE_FILE.parent),
            delete=False,
        ) as handle:
            handle.write(updated)
            temp_name = handle.name

        os.replace(temp_name, BRIDGE_FILE)
        return

    raise RuntimeError("Failed to update bridge file after repeated retries")


def append_activity(text: str, lines: list[str], timestamp: str) -> str:
    block = [f"### {timestamp} | codex"]
    block.extend(f"- {line}" for line in lines)
    stripped = text.rstrip() + "\n\n" + "\n".join(block) + "\n"
    return stripped


def update_task_status(expected_task_id: int, status: str, log_lines: list[str]) -> None:
    timestamp = now_iso()

    def mutator(text: str) -> str:
        current = parse_task(text)
        if current is None:
            raise RuntimeError("Could not parse active task while updating bridge status")
        if current.task_id != expected_task_id:
            if status == "doing":
                raise RuntimeError(
                    f"Bridge task changed from {expected_task_id} to {current.task_id} before work started"
                )
            return append_activity(text, log_lines, timestamp)

        updated = replace_once(text, r"^- Status: .*$", f"- Status: {status}")
        updated = replace_once(updated, r"^- Updated At: .*$", f"- Updated At: {timestamp}")
        return append_activity(updated, log_lines, timestamp)

    mutate_bridge(mutator)


def normalize_summary(text: str, limit: int = 240) -> str:
    compact = " ".join(text.split())
    if not compact:
        return "No summary returned."
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def build_prompt(task: Task) -> str:
    detail_lines = "\n".join(f"- {item}" for item in task.details) if task.details else "- No extra details provided."
    return f"""You are the codex-side bridge worker for `{REPO_ROOT}`.

Execute bridge task `{task.task_id}`.

Constraints:
- Do not edit `.bridge/bridge.md`; the outer bridge monitor owns status and activity log updates.
- You may edit project files in `{REPO_ROOT}` and bridge support files under `.bridge/` if the task requires them.
- Do not revert other people's changes.
- If the task is ambiguous, inspect the repo and make the most reasonable assumption instead of blocking.

Active task:
- Task ID: {task.task_id}
- Assignee: {task.assignee}
- Requested By: {task.requested_by}
- Summary: {task.summary}
- Details:
{detail_lines}

When finished, provide a concise result summary suitable for a bridge activity log.
"""


def run_task(task: Task) -> tuple[int, str]:
    prompt = build_prompt(task)
    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as handle:
        output_path = Path(handle.name)

    cmd = [
        "codex",
        "exec",
        "--cd",
        str(REPO_ROOT),
        "--sandbox",
        "danger-full-access",
        "--ask-for-approval",
        "never",
        "--color",
        "never",
        "-o",
        str(output_path),
        prompt,
    ]

    log(f"starting task {task.task_id} via codex exec")
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"\n[{now_iso()}] task {task.task_id} command: {' '.join(cmd[:-1])} <prompt>\n")
        result = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            stdout=handle,
            stderr=handle,
            text=True,
            check=False,
        )

    try:
        summary = output_path.read_text(encoding="utf-8").strip()
    finally:
        output_path.unlink(missing_ok=True)

    return result.returncode, normalize_summary(summary)


def should_handle(task: Task, last_handled_task_id: int) -> bool:
    return (
        task.task_id > 0
        and task.task_id != last_handled_task_id
        and task.assignee in ASSIGNEES
    )


def monitor() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log(f"codex bridge monitor active for {BRIDGE_FILE}")
    state = load_state()

    while True:
        try:
            if not BRIDGE_FILE.exists():
                log("bridge file missing; waiting for it to appear")
                time.sleep(POLL_INTERVAL)
                continue

            task = parse_task(BRIDGE_FILE.read_text(encoding="utf-8"))
            if task is None:
                log("could not parse active task; retrying")
                time.sleep(POLL_INTERVAL)
                continue

            last_handled = int(state.get("last_handled_task_id", 0))
            if not should_handle(task, last_handled):
                time.sleep(POLL_INTERVAL)
                continue

            update_task_status(task.task_id, "doing", [f"Picked up task {task.task_id}: {task.summary}"])
            exit_code, summary = run_task(task)

            if exit_code == 0:
                update_task_status(task.task_id, "done", [f"Completed task {task.task_id}: {summary}"])
            else:
                update_task_status(
                    task.task_id,
                    "blocked",
                    [f"Task {task.task_id} blocked after codex exec exit code {exit_code}: {summary}"],
                )

            state["last_handled_task_id"] = task.task_id
            save_state(state)
        except KeyboardInterrupt:
            log("monitor interrupted; exiting")
            raise
        except Exception as exc:
            log(f"monitor error: {exc}")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    monitor()

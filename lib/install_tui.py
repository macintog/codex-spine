from __future__ import annotations

import contextlib
import curses
import io
import os
import select
import shlex
import subprocess
import sys
import textwrap
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, Iterator, List, Optional, Sequence, Tuple, Union


@dataclass
class Step:
    label: str
    title: str
    detail: str
    status: str = "pending"
    note: str = ""


class _LogWriter(io.TextIOBase):
    def __init__(self, tui: "InstallTUI", *, level: str) -> None:
        self._tui = tui
        self._level = level
        self._buffer = ""

    def write(self, data: str) -> int:
        self._buffer += data
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._tui.log(line, level=self._level)
        return len(data)

    def flush(self) -> None:
        if self._buffer:
            self._tui.log(self._buffer, level=self._level)
            self._buffer = ""


class InstallTUI:
    def __init__(self, stdscr, *, title: str, subtitle: str, steps: List[Step]) -> None:
        self.stdscr = stdscr
        self.title = title
        self.subtitle = subtitle
        self.steps = steps
        self.current_step = 0
        self.logs: Deque[Tuple[str, str]] = deque(maxlen=400)
        self.footer = "Fullscreen prototype."
        self._init_screen()
        self.render()

    @staticmethod
    def supported() -> bool:
        return sys.stdin.isatty() and sys.stdout.isatty() and os.environ.get("TERM", "dumb") != "dumb"

    def _init_screen(self) -> None:
        curses.noecho()
        curses.cbreak()
        self.stdscr.keypad(True)
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_CYAN, -1)
            curses.init_pair(2, curses.COLOR_GREEN, -1)
            curses.init_pair(3, curses.COLOR_YELLOW, -1)
            curses.init_pair(4, curses.COLOR_RED, -1)
            curses.init_pair(5, curses.COLOR_WHITE, -1)

    def close(self) -> None:
        with contextlib.suppress(curses.error):
            self.stdscr.keypad(False)
            curses.echo()
            curses.nocbreak()
            curses.endwin()

    def color(self, status: str) -> int:
        if not curses.has_colors():
            return curses.A_NORMAL
        mapping = {
            "pending": curses.color_pair(5),
            "in_progress": curses.color_pair(1) | curses.A_BOLD,
            "ok": curses.color_pair(2) | curses.A_BOLD,
            "warn": curses.color_pair(3) | curses.A_BOLD,
            "stop": curses.color_pair(4) | curses.A_BOLD,
            "info": curses.color_pair(1),
        }
        return mapping.get(status, curses.A_NORMAL)

    def step_marker(self, status: str) -> str:
        return {
            "pending": "·",
            "in_progress": "◆",
            "ok": "✓",
            "warn": "!",
            "stop": "×",
        }.get(status, "·")

    def set_step(self, index: int, *, status: str = "in_progress", note: str = "") -> None:
        self.current_step = index
        self.steps[index].status = status
        if note:
            self.steps[index].note = note
        self.render()

    def finish_step(self, index: int, *, status: str, note: str = "") -> None:
        self.steps[index].status = status
        if note:
            self.steps[index].note = note
        self.render()

    def fail_step(self, index: int, *, note: str) -> None:
        self.steps[index].status = "stop"
        self.steps[index].note = note
        self.render()

    def status(self, kind: str, message: str) -> None:
        self.log(f"{self.step_marker(kind)} {message}", level=kind)

    def log(self, message: str, *, level: str = "info") -> None:
        if not message and level == "info":
            return
        for line in message.splitlines() or [""]:
            self.logs.append((level, line))
        self.render()

    @contextlib.contextmanager
    def capture_output(self) -> Iterator[None]:
        stdout_writer = _LogWriter(self, level="info")
        stderr_writer = _LogWriter(self, level="warn")
        with contextlib.redirect_stdout(stdout_writer), contextlib.redirect_stderr(stderr_writer):
            yield
        stdout_writer.flush()
        stderr_writer.flush()

    @contextlib.contextmanager
    def suspend(self, message: str) -> Iterator[None]:
        self.footer = message
        self.render()
        curses.def_prog_mode()
        curses.endwin()
        try:
            yield
        finally:
            self.stdscr.refresh()
            curses.reset_prog_mode()
            try:
                curses.curs_set(0)
            except curses.error:
                pass
        self.footer = "Fullscreen prototype."
        self.render()

    def prompt_yes_no(self, prompt: Union[str, Sequence[str]], *, default: bool) -> bool:
        lines = prompt.splitlines() if isinstance(prompt, str) else [str(line) for line in prompt]
        self.render_modal(lines)
        while True:
            key = self.stdscr.get_wch()
            if isinstance(key, int):
                if key in (
                    curses.KEY_UP,
                    curses.KEY_DOWN,
                    curses.KEY_LEFT,
                    curses.KEY_RIGHT,
                    curses.KEY_RESIZE,
                    curses.KEY_HOME,
                    curses.KEY_END,
                    curses.KEY_NPAGE,
                    curses.KEY_PPAGE,
                ):
                    if key == curses.KEY_RESIZE:
                        self.render_modal(lines)
                    continue
                curses.beep()
                continue
            if isinstance(key, str):
                lowered = key.lower()
                if lowered in ("\n", "\r"):
                    return default
                if lowered == "y":
                    return True
                if lowered == "n":
                    return False
                if lowered == "\x1b":
                    return False
            curses.beep()

    def show_message(self, lines: Sequence[str], *, prompt_hint: str = "Press Enter to continue") -> None:
        footer = self.footer
        self.footer = prompt_hint
        self.render_modal(lines, prompt_hint=prompt_hint)
        while True:
            key = self.stdscr.get_wch()
            if key == curses.KEY_RESIZE:
                self.render_modal(lines, prompt_hint=prompt_hint)
                continue
            if key in ("\n", "\r", " ", "\x1b"):
                break
            if isinstance(key, str) and key.lower() in ("\n", "\r", " ", "\x1b"):
                break
            curses.beep()
        self.footer = footer
        self.render()

    def render_modal(self, lines: Sequence[str], *, prompt_hint: Optional[str] = None) -> None:
        self.render()
        height, width = self.stdscr.getmaxyx()
        body: List[str] = []
        for line in lines:
            body.extend(textwrap.wrap(line, width=max(12, min(width - 12, 68))) or [""])
        box_width = min(width - 6, max(len(line) for line in body) + 4 if body else 24)
        box_height = min(height - 6, len(body) + 4)
        start_y = max(2, (height - box_height) // 2)
        start_x = max(2, (width - box_width) // 2)
        with contextlib.suppress(curses.error):
            self.stdscr.attron(curses.A_BOLD)
        for y in range(box_height):
            for x in range(box_width):
                ch = " "
                if y in (0, box_height - 1):
                    ch = "─" if 0 < x < box_width - 1 else ("┌" if (y, x) == (0, 0) else "┐" if (y, x) == (0, box_width - 1) else "└" if (y, x) == (box_height - 1, 0) else "┘")
                elif x in (0, box_width - 1):
                    ch = "│"
                self._safe_addstr(start_y + y, start_x + x, ch, curses.A_BOLD)
        if prompt_hint:
            hint = prompt_hint[: max(0, box_width - 6)]
            hint_x = max(start_x + 2, start_x + box_width - len(hint) - 2)
            self._safe_addstr(start_y + 1, hint_x, hint, curses.A_DIM)
        text_y = start_y + 2
        for line in body[: max(0, box_height - 4)]:
            self._safe_addstr(text_y, start_x + 2, line, curses.A_NORMAL)
            text_y += 1
        self.stdscr.refresh()

    def run_command(
        self,
        args: Sequence[str],
        *,
        cwd: Optional[Path] = None,
        env: Optional[dict[str, str]] = None,
        heartbeat_message: Optional[str] = None,
        heartbeat_interval: float = 5.0,
        use_terminal: bool = False,
        terminal_intro: Optional[Sequence[str]] = None,
    ) -> None:
        self.log(f"$ {shlex.join([str(part) for part in args])}")
        if use_terminal:
            command = [str(part) for part in args]
            with self.suspend("Terminal handoff in progress below."):
                if terminal_intro:
                    print()
                    for line in terminal_intro:
                        print(line)
                print()
                print("$ {}".format(shlex.join(command)), flush=True)
                try:
                    subprocess.run(
                        command,
                        cwd=str(cwd) if cwd else None,
                        env=env,
                        check=True,
                    )
                except subprocess.CalledProcessError as exc:
                    print()
                    print("codex-spine stopped because the command above failed.", flush=True)
                    print("Press Return to restore the installer.", flush=True)
                    with contextlib.suppress(EOFError):
                        input()
                    self.log("Terminal handoff failed: {}".format(shlex.join(command)), level="stop")
                    raise exc
            self.log("Terminal handoff completed: {}".format(shlex.join(command)), level="ok")
            return
        process = subprocess.Popen(
            [str(part) for part in args],
            cwd=str(cwd) if cwd else None,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        next_heartbeat = time.monotonic() + heartbeat_interval
        stream = process.stdout
        while True:
            ready, _, _ = select.select([stream], [], [], 0.25)
            if ready:
                line = stream.readline()
                if line:
                    self.log(line.rstrip("\n"))
                    next_heartbeat = time.monotonic() + heartbeat_interval
                    continue
            if process.poll() is not None:
                for line in stream.readlines():
                    self.log(line.rstrip("\n"))
                break
            if heartbeat_message and time.monotonic() >= next_heartbeat:
                self.status("info", heartbeat_message)
                next_heartbeat = time.monotonic() + heartbeat_interval
        returncode = process.wait()
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, [str(part) for part in args])

    def render(self) -> None:
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()
        left_width = max(34, min(44, width // 3))
        right_x = left_width + 2
        log_width = max(20, width - right_x - 1)
        content_bottom = max(4, height - 4)
        start_index = 0
        for index, step in enumerate(self.steps):
            if step.status != "ok":
                start_index = index
                break
        else:
            start_index = max(0, len(self.steps) - 1)

        self._safe_addstr(0, 2, self.title, self.color("in_progress"))
        self._safe_addstr(1, 2, self.subtitle, curses.A_DIM)

        self._safe_addstr(3, 2, "Plan", curses.A_BOLD)
        y = 4
        visible_steps = self.steps[start_index:]
        for offset, step in enumerate(visible_steps):
            if y > content_bottom:
                break
            marker = self.step_marker(step.status)
            attrs = self.color(step.status)
            prefix = f"{marker} {step.label}: {step.title}"
            self._safe_addstr(y, 2, prefix[: left_width - 3], attrs)
            y += 1
            for line in textwrap.wrap(step.detail, width=max(10, left_width - 6)) or [""]:
                if y > content_bottom:
                    break
                self._safe_addstr(y, 4, line, curses.A_DIM)
                y += 1
            if step.note:
                for line in textwrap.wrap(step.note, width=max(10, left_width - 6)) or [""]:
                    if y > content_bottom:
                        break
                    self._safe_addstr(y, 4, line, self.color(step.status))
                    y += 1
            if offset != len(visible_steps) - 1:
                y += 1

        self._safe_addstr(3, right_x, "Live Log", curses.A_BOLD)
        log_lines: List[Tuple[str, str]] = []
        for level, line in self.logs:
            wrapped = textwrap.wrap(line, width=log_width) or [""]
            for part in wrapped:
                log_lines.append((level, part))
        visible = log_lines[-max(1, height - 7) :]
        log_y = 4
        for level, line in visible:
            if log_y > content_bottom:
                break
            self._safe_addstr(log_y, right_x, line[:log_width], self.color(level))
            log_y += 1

        self._safe_addstr(height - 2, 2, self.footer[: width - 4], curses.A_DIM)
        self.stdscr.refresh()

    def _safe_addstr(self, y: int, x: int, text: str, attr: int = 0) -> None:
        height, width = self.stdscr.getmaxyx()
        if y < 0 or y >= height or x >= width:
            return
        with contextlib.suppress(curses.error):
            self.stdscr.addstr(y, x, text[: max(0, width - x - 1)], attr)


@contextlib.contextmanager
def open_tui(*, title: str, subtitle: str, steps: List[Step]) -> Iterator[Optional[InstallTUI]]:
    if not InstallTUI.supported():
        yield None
        return
    stdscr = curses.initscr()
    tui = InstallTUI(stdscr, title=title, subtitle=subtitle, steps=steps)
    try:
        yield tui
    finally:
        tui.close()

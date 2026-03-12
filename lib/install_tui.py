from __future__ import annotations

import contextlib
import curses
import io
import os
import pty
import re
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

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
CARET_ANSI_ESCAPE_RE = re.compile(r"\^\[\[[0-?]*[ -/]*[@-~]")
DOWNLOAD_PROGRESS_RE = re.compile(r"^\s*[⏵▶▸▹►]?\s*([^\s]+)\s+\d+(?:\.\d+)?%")
SPINNER_STATUS_RE = re.compile(r"^[.:·⠁-⣿]+\s+(.+)$")
ACTIVITY_FRAMES = ["⠋", "⠙", "⠚", "⠞", "⠖", "⠦", "⠴", "⠲", "⠳", "⠓"]
ACTIVITY_FRAME_INTERVAL = 0.04


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
        self.bottom_panel_title = ""
        self.bottom_panel_lines: List[str] = []
        self.activity_message = ""
        self.activity_frame = 0
        self.activity_updated_at = 0.0
        self.last_modal_size: Optional[Tuple[int, int]] = None
        self.footer = ""
        self.detached_to_terminal = False
        self._closed = False
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
        if self._closed:
            return
        self._closed = True
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

    def reconfigure(
        self,
        *,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
        steps: Optional[List[Step]] = None,
        footer: Optional[str] = None,
        clear_logs: bool = False,
    ) -> None:
        if title is not None:
            self.title = title
        if subtitle is not None:
            self.subtitle = subtitle
        if steps is not None:
            self.steps = steps
            self.current_step = 0
        if footer is not None:
            self.footer = footer
        if clear_logs:
            self.logs.clear()
            self.clear_bottom_panel(render=False)
            self.clear_activity(render=False)
        self.render()

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
        cleaned = _clean_terminal_text(message)
        if not cleaned and level == "info":
            return
        changed = False
        for line in cleaned.splitlines() or [""]:
            line_key = _replacement_key(line)
            if line_key is not None:
                replaced = False
                for index in range(len(self.logs) - 1, -1, -1):
                    _, previous_line = self.logs[index]
                    if _replacement_key(previous_line) == line_key:
                        self.logs[index] = (level, line)
                        replaced = True
                        changed = True
                        break
                if replaced:
                    continue
            if self.logs:
                previous_line = self.logs[-1][1]
                if _normalize_log_line(line) == _normalize_log_line(previous_line):
                    continue
            self.logs.append((level, line))
            changed = True
        if changed:
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
        self.footer = ""
        self.render()

    def prompt_yes_no(self, prompt: Union[str, Sequence[str]], *, default: bool) -> bool:
        lines = prompt.splitlines() if isinstance(prompt, str) else [str(line) for line in prompt]
        self.render_modal(lines)
        while True:
            key = self.stdscr.get_wch()
            if isinstance(key, int):
                if _is_enter_key(key):
                    return default
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
        self.render_modal(lines, prompt_hint=prompt_hint)
        if hasattr(self.stdscr, "nodelay"):
            self.stdscr.nodelay(True)
        try:
            while True:
                key = None
                try:
                    key = self.stdscr.get_wch()
                except curses.error:
                    key = None
                if key == curses.KEY_RESIZE:
                    self.render_modal(lines, prompt_hint=prompt_hint)
                    continue
                if _is_enter_key(key):
                    break
                if key in ("\n", "\r", " ", "\x1b"):
                    break
                if isinstance(key, str) and key.lower() in ("\n", "\r", " ", "\x1b"):
                    break
                if key is not None:
                    curses.beep()
                time.sleep(0.05)
        finally:
            if hasattr(self.stdscr, "nodelay"):
                self.stdscr.nodelay(False)
        self.footer = footer
        self.render()

    def wait_for_acknowledgement(
        self,
        lines: Sequence[str],
        *,
        prompt_hint: str = "Press Enter to continue",
        on_tick=None,
    ) -> None:
        footer = self.footer
        self.render_modal(lines, prompt_hint=prompt_hint)
        if hasattr(self.stdscr, "nodelay"):
            self.stdscr.nodelay(True)
        try:
            while True:
                if on_tick is not None:
                    if on_tick():
                        self.render_modal(lines, prompt_hint=prompt_hint)
                key = None
                try:
                    key = self.stdscr.get_wch()
                except curses.error:
                    key = None
                if key == curses.KEY_RESIZE:
                    self.render_modal(lines, prompt_hint=prompt_hint)
                    continue
                if _is_enter_key(key):
                    break
                if key in ("\n", "\r", " ", "\x1b"):
                    break
                if isinstance(key, str) and key.lower() in ("\n", "\r", " ", "\x1b"):
                    break
                if key is not None:
                    curses.beep()
                time.sleep(0.05)
        finally:
            if hasattr(self.stdscr, "nodelay"):
                self.stdscr.nodelay(False)
        self.footer = footer
        self.render()

    def prompt_text_input(
        self,
        title: str,
        prompt: str,
        *,
        prompt_hint: str = "Type and press Enter",
        modal_size: Optional[Tuple[int, int]] = None,
    ) -> Optional[str]:
        typed: List[str] = []
        needs_full_redraw = True
        while True:
            field = "> {}".format("".join(typed) if typed else "_")
            lines = [title, "", prompt, "", field]
            if needs_full_redraw:
                self.render_modal(lines, prompt_hint=prompt_hint, modal_size=modal_size)
                needs_full_redraw = False
            else:
                layout = self._modal_layout(lines, modal_size=modal_size)
                self._draw_modal(layout, prompt_hint=prompt_hint)
            key = self.stdscr.get_wch()
            if key == curses.KEY_RESIZE:
                needs_full_redraw = True
                continue
            if _is_enter_key(key):
                return "".join(typed)
            if isinstance(key, str):
                if key == "\x1b":
                    return None
                if key in ("\n", "\r"):
                    return "".join(typed)
                if key in ("\x08", "\x7f"):
                    if typed:
                        typed.pop()
                    continue
                if key.isprintable():
                    typed.append(key)
                    continue
            curses.beep()

    def page_text(
        self,
        title: str,
        text: str,
        *,
        prompt_hint: str = "Enter advances; q or Esc cancels",
    ) -> bool:
        height, width = self.stdscr.getmaxyx()
        modal_width = max(28, min(width - 6, 96))
        content_width = max(20, modal_width - 4)
        page_body_limit = max(6, height - 12)
        wrapped_all = _reflow_modal_text(text, width=content_width)
        modal_height = min(height - 6, page_body_limit + 4)
        modal_size = (
            modal_width,
            modal_height,
        )
        self.last_modal_size = modal_size
        page_chunk = max(1, modal_height - 4)
        pages = [
            wrapped_all[index : index + page_chunk]
            for index in range(0, len(wrapped_all), page_chunk)
        ] or [[""]]
        page_index = 0
        while True:
            header = "{} ({}/{})".format(title, page_index + 1, len(pages))
            self.render_modal([header, ""] + pages[page_index], prompt_hint=prompt_hint, modal_size=modal_size)
            key = self.stdscr.get_wch()
            if key == curses.KEY_RESIZE:
                continue
            if _is_enter_key(key):
                if page_index >= len(pages) - 1:
                    return True
                page_index = min(len(pages) - 1, page_index + 1)
                continue
            if key in (curses.KEY_UP, curses.KEY_PPAGE):
                page_index = max(0, page_index - 1)
                continue
            if key in (curses.KEY_DOWN, curses.KEY_NPAGE):
                page_index = min(len(pages) - 1, page_index + 1)
                continue
            if isinstance(key, str):
                lowered = key.lower()
                if lowered == "\x1b" or lowered == "q":
                    return False
                if lowered in ("\n", "\r", " "):
                    if page_index >= len(pages) - 1:
                        return True
                    page_index = min(len(pages) - 1, page_index + 1)
                    continue
            curses.beep()

    def set_bottom_panel(self, title: str, lines: Sequence[str]) -> None:
        self.bottom_panel_title = title
        self.bottom_panel_lines = list(lines)
        self.render()

    def append_bottom_panel_text(self, text: str) -> None:
        cleaned = _clean_terminal_text(text)
        if not cleaned:
            return
        self.bottom_panel_lines.extend(cleaned.splitlines())
        self.bottom_panel_lines = self.bottom_panel_lines[-3:]
        self.render()

    def clear_bottom_panel(self, *, render: bool = True) -> None:
        self.bottom_panel_title = ""
        self.bottom_panel_lines = []
        if render:
            self.render()

    def pulse_activity(self, message: str, *, render: bool = True) -> bool:
        now = time.monotonic()
        if message != self.activity_message:
            self.activity_message = message
            self.activity_frame = 0
            self.activity_updated_at = now
            if render:
                self.render()
            return True
        return self.tick_activity(now=now, render=render)

    def tick_activity(self, *, now: Optional[float] = None, render: bool = True) -> bool:
        if not self.activity_message:
            return False
        if now is None:
            now = time.monotonic()
        if self.activity_updated_at == 0.0:
            self.activity_updated_at = now
            return False
        elapsed = now - self.activity_updated_at
        if elapsed < ACTIVITY_FRAME_INTERVAL:
            return False
        frames = max(1, int(elapsed / ACTIVITY_FRAME_INTERVAL))
        self.activity_frame = (self.activity_frame + frames) % len(ACTIVITY_FRAMES)
        self.activity_updated_at += frames * ACTIVITY_FRAME_INTERVAL
        if render:
            self.render()
        return True

    def clear_activity(self, *, render: bool = True) -> bool:
        if self.activity_message:
            self.activity_message = ""
            self.activity_updated_at = 0.0
            if render:
                self.render()
            return True
        return False

    def render_modal(
        self,
        lines: Sequence[str],
        *,
        prompt_hint: Optional[str] = None,
        modal_size: Optional[Tuple[int, int]] = None,
    ) -> None:
        self.render()
        self._draw_modal(self._modal_layout(lines, modal_size=modal_size), prompt_hint=prompt_hint)

    def _modal_layout(
        self,
        lines: Sequence[str],
        *,
        modal_size: Optional[Tuple[int, int]] = None,
    ) -> Tuple[int, int, int, int, List[str]]:
        height, width = self.stdscr.getmaxyx()
        wrap_width = max(12, (modal_size[0] - 4) if modal_size is not None else min(width - 12, 68))
        body: List[str] = []
        for line in lines:
            body.extend(textwrap.wrap(line, width=wrap_width) or [""])
        if modal_size is None:
            box_width = min(width - 6, max(len(line) for line in body) + 4 if body else 24)
            box_height = min(height - 6, len(body) + 4)
        else:
            box_width, box_height = modal_size
        start_y = max(2, (height - box_height) // 2)
        start_x = max(2, (width - box_width) // 2)
        return start_y, start_x, box_width, box_height, body

    def _draw_modal(
        self,
        layout: Tuple[int, int, int, int, List[str]],
        *,
        prompt_hint: Optional[str] = None,
    ) -> None:
        start_y, start_x, box_width, box_height, body = layout
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
            text=False,
            bufsize=0,
        )
        assert process.stdout is not None
        next_heartbeat = time.monotonic() + heartbeat_interval
        stream = process.stdout
        fd = stream.fileno()
        buffer = ""
        if heartbeat_message:
            self.pulse_activity(heartbeat_message)
        while True:
            self.tick_activity()
            ready, _, _ = select.select([fd], [], [], 0.25)
            if ready:
                chunk = os.read(fd, 4096)
                if chunk:
                    buffer += chunk.decode("utf-8", errors="replace")
                    while True:
                        newline_index = buffer.find("\n")
                        carriage_index = buffer.find("\r")
                        if newline_index == -1 and carriage_index == -1:
                            break
                        split_index = min(
                            index
                            for index in (newline_index, carriage_index)
                            if index != -1
                        )
                        self.log(buffer[:split_index])
                        buffer = buffer[split_index + 1 :]
                    next_heartbeat = time.monotonic() + heartbeat_interval
                    continue
            if process.poll() is not None:
                remainder = stream.read()
                if remainder:
                    buffer += remainder.decode("utf-8", errors="replace")
                if buffer:
                    self.log(buffer.rstrip("\n\r"))
                break
            if heartbeat_message and time.monotonic() >= next_heartbeat:
                self.pulse_activity(heartbeat_message)
                next_heartbeat = time.monotonic() + heartbeat_interval
        returncode = process.wait()
        self.clear_activity()
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, [str(part) for part in args])

    def run_bottom_prompt_command(
        self,
        args: Sequence[str],
        *,
        cwd: Optional[Path] = None,
        env: Optional[dict[str, str]] = None,
        panel_title: str,
        intro_lines: Sequence[str],
    ) -> None:
        command = [str(part) for part in args]
        self.log("$ {}".format(shlex.join(command)))
        master_fd, slave_fd = pty.openpty()
        self.set_bottom_panel(panel_title, intro_lines)
        process = subprocess.Popen(
            command,
            cwd=str(cwd) if cwd else None,
            env=env,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            text=False,
            close_fds=True,
        )
        os.close(slave_fd)
        if hasattr(self.stdscr, "nodelay"):
            self.stdscr.nodelay(True)
        try:
            while True:
                ready, _, _ = select.select([master_fd], [], [], 0.05)
                if ready:
                    chunk = os.read(master_fd, 1024)
                    if chunk:
                        self.append_bottom_panel_text(chunk.decode("utf-8", errors="replace"))
                try:
                    key = self.stdscr.get_wch()
                except curses.error:
                    key = None
                if key == curses.KEY_RESIZE:
                    self.render()
                elif isinstance(key, str):
                    if key in ("\n", "\r"):
                        os.write(master_fd, b"\n")
                    elif key in ("\x08", "\x7f"):
                        os.write(master_fd, b"\x7f")
                    elif key == "\x03":
                        os.write(master_fd, b"\x03")
                    elif key.isprintable():
                        os.write(master_fd, key.encode("utf-8"))
                elif _is_enter_key(key):
                    os.write(master_fd, b"\n")
                if process.poll() is not None:
                    break
            returncode = process.wait()
        finally:
            if hasattr(self.stdscr, "nodelay"):
                self.stdscr.nodelay(False)
            os.close(master_fd)
            self.clear_bottom_panel()
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command)

    def render(self) -> None:
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()
        left_width = 38 if width >= 90 else max(30, min(38, (width // 2) - 4))
        right_x = left_width + 2
        log_width = max(20, width - right_x - 1)
        plan_header_y = 2 if not self.subtitle else 3
        plan_start_y = plan_header_y + 1
        bottom_panel_height = 0
        if self.bottom_panel_title or self.bottom_panel_lines:
            bottom_panel_height = min(5, max(4, len(self.bottom_panel_lines) + 2))
        content_bottom = max(4, height - 4 - bottom_panel_height)
        plan_available_lines = max(1, content_bottom - plan_start_y + 1)

        self._safe_addstr(0, 2, self.title, self.color("in_progress"))
        if self.subtitle:
            self._safe_addstr(1, 2, self.subtitle, curses.A_DIM)

        self._safe_addstr(plan_header_y, 2, "Plan", curses.A_BOLD)
        y = plan_start_y
        visible_steps = self.steps[:]
        while visible_steps and self._steps_render_height(visible_steps, left_width=left_width) > plan_available_lines:
            visible_steps = visible_steps[1:]
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

        self._safe_addstr(plan_header_y, right_x, "Live Log", curses.A_BOLD)
        log_lines: List[Tuple[str, str]] = []
        for level, line in self.logs:
            wrapped = textwrap.wrap(_clean_terminal_text(line), width=log_width) or [""]
            for part in wrapped:
                log_lines.append((level, part))
        visible = log_lines[-max(1, height - (plan_start_y + 3)) :]
        log_y = plan_start_y
        for level, line in visible:
            if log_y > content_bottom:
                break
            self._safe_addstr(log_y, right_x, line[:log_width], self.color(level))
            log_y += 1

        if bottom_panel_height:
            panel_top = height - 2 - bottom_panel_height
            panel_y = panel_top
            if self.bottom_panel_title:
                self._safe_addstr(panel_top, 2, self.bottom_panel_title[: width - 4], curses.A_BOLD)
                panel_y += 1
            visible_lines = self.bottom_panel_lines[-max(1, bottom_panel_height - (1 if self.bottom_panel_title else 0)) :]
            for line in visible_lines:
                self._safe_addstr(panel_y, 2, line[: width - 4], curses.A_NORMAL)
                panel_y += 1

        footer_text = self.footer
        if self.activity_message:
            spinner = ACTIVITY_FRAMES[self.activity_frame]
            footer_text = "{} {}".format(spinner, self.activity_message)
        self._safe_addstr(height - 2, 2, footer_text[: width - 4], curses.A_DIM)
        self.stdscr.refresh()

    def _safe_addstr(self, y: int, x: int, text: str, attr: int = 0) -> None:
        height, width = self.stdscr.getmaxyx()
        if y < 0 or y >= height or x >= width:
            return
        with contextlib.suppress(curses.error):
            self.stdscr.addstr(y, x, text[: max(0, width - x - 1)], attr)

    def _steps_render_height(self, steps: Sequence[Step], *, left_width: int) -> int:
        total = 0
        for index, step in enumerate(steps):
            total += self._step_render_height(step, left_width=left_width, is_last=index == len(steps) - 1)
        return total

    def _step_render_height(self, step: Step, *, left_width: int, is_last: bool) -> int:
        detail_lines = textwrap.wrap(step.detail, width=max(10, left_width - 6)) or [""]
        note_lines = textwrap.wrap(step.note, width=max(10, left_width - 6)) or []
        height = 1 + len(detail_lines) + len(note_lines)
        if not is_last:
            height += 1
        return height


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


def _clean_terminal_text(text: str) -> str:
    text = ANSI_ESCAPE_RE.sub("", text)
    text = CARET_ANSI_ESCAPE_RE.sub("", text)
    lines: List[str] = []
    current: List[str] = []
    for char in text:
        if char == "\r":
            current = []
            continue
        if char in ("\x08", "\x7f"):
            if current:
                current.pop()
            continue
        if char == "\n":
            lines.append("".join(current))
            current = []
            continue
        if char == "\t" or ord(char) >= 32:
            current.append(char)
    if current:
        lines.append("".join(current))
    return "\n".join(lines)


def _reflow_modal_text(text: str, *, width: int) -> List[str]:
    blocks: List[str] = []
    paragraph: List[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if not paragraph:
            return
        blocks.extend(textwrap.wrap(" ".join(paragraph), width=width) or [""])
        paragraph = []

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            flush_paragraph()
            if blocks and blocks[-1] != "":
                blocks.append("")
            continue
        if stripped.startswith(("- ", "* ", "• ", "#")) or re.match(r"\d+\.\s", stripped):
            flush_paragraph()
            blocks.extend(textwrap.wrap(stripped, width=width, subsequent_indent="  ") or [""])
            continue
        paragraph.append(stripped)
    flush_paragraph()
    return blocks or [""]


def _normalize_log_line(text: str) -> str:
    return " ".join(text.strip().split())


def _replacement_key(text: str) -> Optional[str]:
    compact = _normalize_log_line(text)
    if not compact:
        return None
    progress_match = DOWNLOAD_PROGRESS_RE.match(compact)
    if progress_match:
        return f"download-progress:{progress_match.group(1)}"
    spinner_match = SPINNER_STATUS_RE.match(compact)
    if spinner_match:
        return f"spinner:{spinner_match.group(1)}"
    return None


def _is_enter_key(key: object) -> bool:
    return key == curses.KEY_ENTER or key in (10, 13)

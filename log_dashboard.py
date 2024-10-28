import os
import sys
import time
import json
import curses
import threading
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set
from collections import deque

class LogMonitor:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.log_files = {}
        self.file_positions = {}
        self.log_buffers = {}
        self.error_buffers = {}  # New: separate buffer for error messages
        self.buffer_size = 1000
        self.error_buffer_size = 500  # New: size for error buffer
        self.running = True
        self.current_view = 'logs'  # New: toggle between 'logs' and 'errors'
        self.error_pattern = re.compile(r'error', re.IGNORECASE)  # New: pattern for matching errors
        self.load_config()

    def load_config(self) -> None:
        """Load log file paths from JSON configuration file."""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                self.log_files = {
                    name: Path(path).expanduser().resolve()
                    for name, path in config['log_files'].items()
                }
        except Exception as e:
            print(f"Error loading config: {e}")
            sys.exit(1)

        # Initialize buffers and positions
        for name in self.log_files:
            self.log_buffers[name] = deque(maxlen=self.buffer_size)
            self.error_buffers[name] = deque(maxlen=self.error_buffer_size)  # New: error buffer
            self.file_positions[name] = 0

    def is_error_message(self, line: str) -> bool:
        """Check if a line contains an error message."""
        return bool(self.error_pattern.search(line))

    def monitor_file(self, name: str, path: Path) -> None:
        """Monitor a single log file for changes."""
        while self.running:
            try:
                if not path.exists():
                    time.sleep(1)
                    continue

                with open(path, 'r') as f:
                    f.seek(self.file_positions[name])
                    new_lines = f.readlines()
                    if new_lines:
                        for line in new_lines:
                            timestamp = datetime.now().strftime('%H:%M:%S')
                            formatted_line = f"[{timestamp}] {line.strip()}"
                            self.log_buffers[name].append(formatted_line)

                            # Check for errors and add to error buffer if found
                            if self.is_error_message(line):
                                self.error_buffers[name].append(
                                    f"[{timestamp}] {name}: {line.strip()}"
                                )

                        self.file_positions[name] = f.tell()
                time.sleep(0.1)
            except Exception as e:
                error_msg = f"Error reading file: {e}"
                self.log_buffers[name].append(error_msg)
                self.error_buffers[name].append(error_msg)
                time.sleep(1)

    def start_monitoring(self) -> None:
        """Start monitoring all configured log files."""
        threads = []
        for name, path in self.log_files.items():
            thread = threading.Thread(
                target=self.monitor_file,
                args=(name, path),
                daemon=True
            )
            threads.append(thread)
            thread.start()

        try:
            self.display_dashboard()
        except KeyboardInterrupt:
            self.running = False
            for thread in threads:
                thread.join()

    def display_dashboard(self) -> None:
        """Display the ASCII dashboard using curses."""
        def draw_box(win, y: int, x: int, height: int, width: int) -> None:
            """Draw a box with ASCII characters."""
            win.addstr(y, x, '┌' + '─' * (width - 2) + '┐')
            for i in range(1, height - 1):
                win.addstr(y + i, x, '│')
                win.addstr(y + i, x + width - 1, '│')
            win.addstr(y + height - 1, x, '└' + '─' * (width - 2) + '┘')

        def init_colors() -> None:
            """Initialize color pairs."""
            curses.start_color()
            curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)    # Header
            curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)   # File names
            curses.init_pair(3, curses.COLOR_CYAN, curses.COLOR_BLACK)     # Instructions
            curses.init_pair(4, curses.COLOR_RED, curses.COLOR_BLACK)      # Errors
            curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_RED)      # Error count

        def display_logs(stdscr, height: int, width: int) -> None:
            """Display regular log view."""
            log_height = (height - 4) // len(self.log_files)
            current_y = 2

            for name, path in self.log_files.items():
                draw_box(stdscr, current_y, 0, log_height, width)

                # Display log file name, path, and error count
                error_count = len(self.error_buffers[name])
                title = f" {name} - {path} "
                error_badge = f" {error_count} errors " if error_count > 0 else ""

                stdscr.addstr(current_y, 2, title, curses.color_pair(2))
                if error_count > 0:
                    stdscr.addstr(current_y, len(title) + 2, error_badge,
                                curses.color_pair(5) | curses.A_BOLD)

                # Display log content
                display_lines = list(self.log_buffers[name])[-log_height+3:]
                for i, line in enumerate(display_lines):
                    if current_y + i + 1 < height - 1:
                        try:
                            # Highlight error messages in red
                            if self.is_error_message(line):
                                stdscr.addnstr(
                                    current_y + i + 1, 2, line, width - 4,
                                    curses.color_pair(4) | curses.A_BOLD
                                )
                            else:
                                stdscr.addnstr(current_y + i + 1, 2, line, width - 4)
                        except curses.error:
                            pass

                current_y += log_height

        def display_errors(stdscr, height: int, width: int) -> None:
            """Display error view."""
            # Combine all error messages from all files
            all_errors = []
            for name, errors in self.error_buffers.items():
                all_errors.extend(list(errors))

            # Sort errors by timestamp
            all_errors.sort(reverse=True)

            # Display error summary
            total_errors = sum(len(errors) for errors in self.error_buffers.values())
            summary = f" Error Summary (Total: {total_errors}) "
            draw_box(stdscr, 2, 0, height - 3, width)
            stdscr.addstr(2, 2, summary, curses.color_pair(4) | curses.A_BOLD)

            # Display errors
            for i, error in enumerate(all_errors):
                if i + 4 < height - 1:
                    try:
                        stdscr.addnstr(i + 4, 2, error, width - 4,
                                     curses.color_pair(4))
                    except curses.error:
                        pass

        def main(stdscr):
            init_colors()
            curses.curs_set(0)
            stdscr.timeout(100)

            while self.running:
                stdscr.clear()
                height, width = stdscr.getmaxyx()

                # Draw header
                header = " Log File Monitor "
                stdscr.addstr(0, (width - len(header)) // 2, header,
                            curses.color_pair(1) | curses.A_BOLD)

                # Display monitoring status and instructions
                status = f"Monitoring {len(self.log_files)} files"
                stdscr.addstr(1, 2, status, curses.color_pair(2))

                instructions = "Press 'q' to quit | 'e' to toggle error view"
                stdscr.addstr(1, width - len(instructions) - 2, instructions,
                            curses.color_pair(3))

                # Display current view
                if self.current_view == 'logs':
                    display_logs(stdscr, height, width)
                else:
                    display_errors(stdscr, height, width)

                stdscr.refresh()

                # Handle user input
                try:
                    key = stdscr.getch()
                    if key == ord('q'):
                        self.running = False
                    elif key == ord('e'):
                        self.current_view = 'errors' if self.current_view == 'logs' else 'logs'
                except curses.error:
                    pass

        curses.wrapper(main)

def main():
    if len(sys.argv) != 2:
        print("Usage: python log_monitor.py <config_file>")
        sys.exit(1)

    monitor = LogMonitor(sys.argv[1])
    monitor.start_monitoring()

if __name__ == "__main__":
    main()

# pure_arch/utils/logger.py
import logging
import os
import sys
from typing import Optional

# Import Typer/Rich components
from rich.console import Console
from rich.text import Text
from rich.status import Status
from rich.logging import RichHandler

# --- 1. Custom Log Levels (Kept for File Logging Consistency) ---
SECTION_LEVEL_NUM = 25
EXECUTE_LEVEL_NUM = 26
logging.addLevelName(SECTION_LEVEL_NUM, 'SECTION')
logging.addLevelName(EXECUTE_LEVEL_NUM, 'EXECUTE')

# --- 2. File Formatter (Modified from your original) ---
class FileFormatter(logging.Formatter):
    """
    Detailed formatter for file output. Excludes colors.
    """
    def format(self, record):
        # Prepare fixed-width attributes for consistent file structure
        record.levelname_fixed = f"{record.levelname:<9}"
        record.name_fixed = f"{record.name:<15}"
        record.filename_fixed = f"{record.filename:<20}"
        record.lineno_fixed = f"{record.lineno:<5}"

        # Standard format string using the fixed-width attributes
        fmt = '%(asctime)s - %(levelname_fixed)s - %(name_fixed)s - %(filename_fixed)s:%(lineno_fixed)s - %(message)s'
        self._style._fmt = fmt

        return super().format(record)

# --- 3. AppLogger Wrapper (Standard Logger, Rich Console, and Status Manager) ---
class RichAppLogger:
    """
    Manages both standard logging (for files) and Rich Console output (for TUI).
    It replaces the AppLogger class.
    """
    def __init__(self, app_name: str, console: Console, logger: logging.Logger):
        self.console = console
        self.logger = logger
        self._current_status: Optional[Status] = None # Stores the Rich Status object

    def _log_and_print(self, level: int, console_message: Text, file_message: str):
        """Helper to ensure a message is printed to the TUI and logged to file."""
        # 1. TUI Output (Rich): Prints the styled message
        self.console.print(console_message)
        # 2. File Output (Logging): Logs the message at the specified level
        self.logger.log(level, file_message)

    def section(self, message: str, *args, **kwargs):
        """Logs a message with the custom SECTION level, styled for the TUI."""
        # Ensure any pending EXECUTE status is stopped before printing a new section
        self._stop_current_status()

        # TUI: Print a bold, yellow section header
        console_msg = Text(f"SECTION: {message}", style="bold yellow on black")

        # File: Log the simple message
        self.logger.log(SECTION_LEVEL_NUM, f"SECTION: {message}")
        self.console.print(console_msg)

    def execute(self, message: str, success: Optional[bool] = None):
        """
        Displays EXECUTE status on the console using Rich's Status,
        and logs the start/completion status to the file.
        """
        file_message = ""

        if success is None: # Initial call: [EXECUTING]
            self._stop_current_status() # Ensure any previous status is stopped

            # Start a new Rich Status for live display
            self._current_status = self.console.status(f"[bold green][INSTALLING] {message}[/]", spinner="dots")
            self._current_status.start()
            file_message = f"[EXECUTING] {message}"

        elif success is True: # Completion: [COMPLETED]
            if self._current_status:
                self._current_status.stop()
            # TUI: Overwrite the status line with a final message
            self.console.print(f"[green]✔ [COMPLETED][/green] {message}")
            self._current_status = None # Clear status
            file_message = f"[COMPLETED] {message}"

        elif success is False: # Failure: [FAILED]
            if self._current_status:
                self._current_status.stop()
            # TUI: Overwrite the status line with a final message
            self.console.print(f"[bold red]✘ [FAILED][/bold red] {message}")
            self._current_status = None # Clear status
            file_message = f"[FAILED] {message}"

        # Always log the event to the file
        self.logger.log(EXECUTE_LEVEL_NUM, file_message)

    def info(self, message, *args, **kwargs):
        """Standard log messages, ensuring status is stopped first."""
        self._stop_current_status()
        self.logger.info(message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        """Standard log messages, ensuring status is stopped first."""
        self._stop_current_status()
        self.logger.warning(message, *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        """Standard log messages, ensuring status is stopped first."""
        self._stop_current_status()
        self.logger.debug(message, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        """Standard log messages, ensuring status is stopped first."""
        self._stop_current_status()
        self.logger.critical(message, *args, **kwargs)

    # --- Other standard logging methods would be added here (e.g., error, debug) ---
    def error(self, message, *args, **kwargs):
        self._stop_current_status()
        self.logger.error(message, *args, **kwargs)

    def _stop_current_status(self):
        """Stops the current Rich Status bar and prints a newline if necessary."""
        if self._current_status:
            self._current_status.stop()
            self._current_status = None

# --- 4. Initialization Routine ---
def initialize_app_logger(
    app_name: str,
    log_directory: str = "logs",
    log_file_name: str = "application.log",
    file_log_level: int = logging.DEBUG,
) -> RichAppLogger:
    """
    Initializes and configures standard logging for file output, and sets up
    the Rich Console for TUI output.
    """
    # 1. Standard Logger Setup (Only for file handler)
    logger = logging.getLogger(app_name)
    logger.setLevel(logging.DEBUG) # Lowest level for full capture
    logger.propagate = False

    # Clear existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # 2. File Handler Setup
    os.makedirs(log_directory, exist_ok=True)
    log_file_path = os.path.join(log_directory, log_file_name)

    file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
    file_handler.setLevel(file_log_level)
    file_formatter = FileFormatter() # FileFormatter handles the fixed-width format
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # 3. Rich Console/Stream Handler Setup (Optional, using RichHandler for standard logs)
    # Note: We don't use RichHandler for console in the same way,
    # but we can add a basic StreamHandler if needed.
    # The console print is handled directly by RichAppLogger for simplicity.

    # 4. Rich Console Setup
    # Typer uses a global Console, which we instantiate here for our wrapper.
    console = Console(file=sys.stderr, # Use stderr for console output as per best practice
                      force_terminal=True,
                      soft_wrap=True)

    return RichAppLogger(app_name, console, logger)

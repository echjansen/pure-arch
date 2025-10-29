import logging
import os
import sys
from typing import Optional
from contextlib import contextmanager

# Import Typer/Rich components
from rich.console import Console
from rich.text import Text
from rich.status import Status
from rich.logging import RichHandler
from rich.theme import Theme

# --- 1. Custom Log Levels and Subclassed Logger ---
# Define custom levels (must be done before setting LoggerClass)
SECTION_LEVEL_NUM = 25
EXECUTE_LEVEL_NUM = 26
logging.addLevelName(SECTION_LEVEL_NUM, 'SECTION')
logging.addLevelName(EXECUTE_LEVEL_NUM, 'EXECUTE')


class AppLogger(logging.Logger):
    """
    Subclasses logging.Logger to add custom methods for SECTION and EXECUTE levels.
    """

    def section(self, msg, *args, **kwargs):
        """Logs a message at the SECTION level."""
        if self.isEnabledFor(SECTION_LEVEL_NUM):
            self._log(SECTION_LEVEL_NUM, msg, args, **kwargs)

    def execute(self, msg, *args, **kwargs):
        """Logs a message at the EXECUTE level."""
        if self.isEnabledFor(EXECUTE_LEVEL_NUM):
            self._log(EXECUTE_LEVEL_NUM, msg, args, **kwargs)


# Set the custom logger class globally
logging.setLoggerClass(AppLogger)


# --- 2. File Formatter (For consistent file structure) ---
class FileFormatter(logging.Formatter):
    """
    Detailed formatter for file output.
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


# --- 3. RichAppLogger Wrapper (Focuses on TUI presentation) ---
class RichAppLogger:
    """
    Manages TUI output via Rich Console and wraps the AppLogger instance.
    """

    def __init__(self, console: Console, logger: AppLogger):
        self.console = console
        self.logger: AppLogger = logger
        self._theme = Theme({"section": "bold yellow on black"})

    def section(self, message: str, *args, **kwargs):
        """Logs a message with the custom SECTION level and prints a styled header to TUI."""
        # TUI: Print a bold, yellow section header
        console_msg = Text(f"SECTION: {message}", style="section")
        self.console.print(console_msg)

        # File: Log using the custom logger method (this is NOT filtered)
        self.logger.section(f"SECTION: {message}", *args, **kwargs)

    @contextmanager
    def execution_step(self, message: str):
        """
        Context manager for a live Rich Status display, ensuring the
        [RUNNING] status is overwritten by the final [COMPLETED]/[CRITICAL] message.
        """

        # 1. Start the TUI live status spinner. This is the ephemeral line.
        with self.console.status(f"[bold green]...[/] [RUNNING] {message}", spinner="dots") as status:

            # Log the start to file. This will NOT be printed to console due to the filter.
            self.logger.execute(f"[RUNNING] {message}")

            try:
                # 2. Yield to the execution block (e.g., executor.execute_command)
                yield status

                # 3. On successful exit: Overwrite the TUI line with the permanent success message.
                self.console.print(f"[green]✔ [COMPLETED][/green] {message}")
                self.logger.execute(f"[COMPLETED] {message}")

            except Exception as e:
                # 4. On failure/exception: Overwrite the TUI line with the permanent failure message.

                # Check for expected command failure (ShellCommandError, etc.)
                is_critical = issubclass(type(e), Exception) and 'ShellCommandError' in globals() and isinstance(e, globals()['ShellCommandError'])
                status_tag = "[CRITICAL]" if is_critical else "[FAILED]"

                # Print the final, permanent failure message
                self.console.print(f"[bold red]✘ {status_tag}[/bold red] {message}")
                self.logger.execute(f"{status_tag} {message}")

                # Ensure the exception is logged to file with full traceback
                self.logger.exception(f"Exception during execution step: {message}")

                # Use Rich's traceback rendering for TUI visibility
                if not is_critical:
                    self.console.print("\n[bold red]Traceback (most recent call last):[/bold red]")
                    self.console.print_exception(show_locals=True)

                raise # Re-raise the exception to be handled upstream

    # --- Standard Logging Wrappers (Simple pass-through to logger) ---

    def info(self, message, *args, **kwargs):
        self.logger.info(message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        self.logger.warning(message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        self.logger.error(message, *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        self.logger.debug(message, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        self.logger.critical(message, *args, **kwargs)

    def exception(self, message, *args, **kwargs):
        """Logs an ERROR to file with traceback and prints a rich traceback to the console."""
        self.logger.exception(message, *args, **kwargs)
        self.console.print(f"[bold red]FATAL ERROR: {message}[/bold red]")
        self.console.print_exception(show_locals=True)


# --- 5. Custom Filter to Exclude EXECUTE Level ---

class ExecuteFilter(logging.Filter):
    """
    Excludes logs at the EXECUTE level from being processed by the handler.
    This prevents RichHandler from printing duplicate [RUNNING] and [COMPLETED]
    messages to the TUI, which are already handled by the execution_step context manager.
    """
    def filter(self, record):
        return record.levelno != EXECUTE_LEVEL_NUM

# --- 6. Initialization Routine ---
def initialize_app_logger(
    app_name: str,
    log_directory: str = "logs",
    log_file_name: str = "application.log",
    file_log_level: int = logging.DEBUG,
    console_log_level: int = logging.INFO,
) -> RichAppLogger:
    """
    Initializes and configures the AppLogger for file output and Rich Console for TUI.
    """
    logger: AppLogger = logging.getLogger(app_name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # 1. File Handler Setup
    os.makedirs(log_directory, exist_ok=True)
    log_file_path = os.path.join(log_directory, log_file_name)

    file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
    file_handler.setLevel(file_log_level)
    file_formatter = FileFormatter()
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # 2. Rich Console Setup
    console = Console(file=sys.stderr, force_terminal=True, soft_wrap=True)

    # 3. Rich Handler Setup (For standard logs: INFO, WARNING, ERROR, etc.)
    stream_handler = RichHandler(
        console=console,
        show_time=False,
        show_level=True,
        show_path=False,
        keywords=[],
        level=console_log_level
    )

    # CRITICAL FIX: Apply the filter to stop the RichHandler from duplicating EXECUTE messages
    stream_handler.addFilter(ExecuteFilter())

    logger.addHandler(stream_handler)

    # 4. Instantiate and return the wrapper
    return RichAppLogger(console, logger)



# # pure_arch/utils/logger.py
# import logging
# import os
# import sys
# from typing import Optional
# from contextlib import contextmanager

# # Import Typer/Rich components
# from rich.console import Console
# from rich.text import Text
# from rich.status import Status
# from rich.logging import RichHandler
# from rich.theme import Theme

# # --- 1. Custom Log Levels and Subclassed Logger ---
# # Define custom levels (must be done before setting LoggerClass)
# SECTION_LEVEL_NUM = 25
# EXECUTE_LEVEL_NUM = 26
# logging.addLevelName(SECTION_LEVEL_NUM, 'SECTION')
# logging.addLevelName(EXECUTE_LEVEL_NUM, 'EXECUTE')


# class AppLogger(logging.Logger):
#     """
#     Subclasses logging.Logger to add custom methods for SECTION and EXECUTE levels.
#     This ensures these methods are available on the standard logger instance.
#     """

#     def section(self, msg, *args, **kwargs):
#         """Logs a message at the SECTION level."""
#         if self.isEnabledFor(SECTION_LEVEL_NUM):
#             self._log(SECTION_LEVEL_NUM, msg, args, **kwargs)

#     def execute(self, msg, *args, **kwargs):
#         """Logs a message at the EXECUTE level."""
#         if self.isEnabledFor(EXECUTE_LEVEL_NUM):
#             self._log(EXECUTE_LEVEL_NUM, msg, args, **kwargs)


# # Set the custom logger class globally
# logging.setLoggerClass(AppLogger)


# # --- 2. File Formatter (For consistent file structure) ---
# class FileFormatter(logging.Formatter):
#     """
#     Detailed formatter for file output. Prepares fixed-width attributes
#     by leveraging the logging.Formatter structure.
#     """

#     def format(self, record):
#         # Prepare fixed-width attributes for consistent file structure
#         # NOTE: This temporary attribute creation is the practical way to apply
#         # fixed-width formatting without changing the logging.Formatter internal style.
#         record.levelname_fixed = f"{record.levelname:<9}"
#         record.name_fixed = f"{record.name:<15}"
#         record.filename_fixed = f"{record.filename:<20}"
#         record.lineno_fixed = f"{record.lineno:<5}"

#         # Standard format string using the fixed-width attributes
#         fmt = '%(asctime)s - %(levelname_fixed)s - %(name_fixed)s - %(filename_fixed)s:%(lineno_fixed)s - %(message)s'
#         self._style._fmt = fmt

#         return super().format(record)


# # --- 3. RichAppLogger Wrapper (Focuses on TUI presentation) ---
# class RichAppLogger:
#     """
#     Manages TUI output via Rich Console and wraps the AppLogger instance.
#     It provides presentation methods like section() and the execution_step
#     context manager.
#     """

#     def __init__(self, console: Console, logger: AppLogger):
#         self.console = console
#         # Note: The logger is now an instance of AppLogger with custom methods
#         self.logger: AppLogger = logger
#         self._current_status: Optional[Status] = None
#         # Use a custom theme for TUI messages if desired
#         self._theme = Theme({"section": "bold yellow on black"})

#     def section(self, message: str, *args, **kwargs):
#         """Logs a message with the custom SECTION level and prints a styled header to TUI."""
#         self._stop_current_status()

#         # TUI: Print a bold, yellow section header
#         console_msg = Text(f"SECTION: {message}", style="section")
#         self.console.print(console_msg)

#         # File: Log using the custom logger method
#         self.logger.section(f"SECTION: {message}", *args, **kwargs)

#     # @contextmanager
#     # def execution_step(self, message: str):
#     #     """
#     #     Context manager for a live Rich Status display, logging start/completion/failure.
#     #     Example: with logger.execution_step("Installing package X"): ...
#     #     """
#     #     # 1. Log the start to file
#     #     self.logger.execute(f"[EXECUTING] {message}")

#     #     # 2. Start the TUI status
#     #     # Note: Using the console's status context manager for safety
#     #     with self.console.status(f"[bold green]...[/] {message}", spinner="dots") as status:
#     #         try:
#     #             # 3. Yield to the execution block
#     #             yield status

#     #             # 4. On successful exit (no exception)
#     #             self.console.print(f"[green]✔ [COMPLETED][/green] {message}")
#     #             self.logger.execute(f"[COMPLETED] {message}")

#     #         except Exception:
#     #             # 5. On failure/exception
#     #             self.console.print(f"[bold red]✘ [FAILED][/bold red] {message}")
#     #             self.logger.execute(f"[FAILED] {message}")

#     #             # Use Rich's traceback rendering for TUI visibility
#     #             self.console.print("\n[bold red]Traceback (most recent call last):[/bold red]")
#     #             self.console.print_exception(show_locals=True)

#     #             # Ensure the exception is logged to file with full traceback
#     #             # Note: logger.exception is error() with exc_info=True
#     #             self.logger.exception(f"Exception during execution step: {message}")

#     #             raise # Re-raise the exception to be handled upstream

#     @contextmanager
#     def execution_step(self, message: str):
#         """
#         Context manager for a live Rich Status display, ensuring the
#         [RUNNING] status is overwritten by the final [COMPLETED]/[CRITICAL] message.
#         """

#         # 1. Start the TUI live status spinner. This line is the one that will be
#         #    cleared/overwritten when the 'with' block exits.
#         #    The Status API handles the 'overwrite' by making this line ephemeral.
#         with self.console.status(f"[bold green]...[/] [RUNNING] {message}", spinner="dots") as status:

#             # Log the start to file
#             self.logger.execute(f"[RUNNING] {message}")

#             try:
#                 # 2. Yield to the execution block (e.g., executor.execute_command)
#                 yield status

#                 # 3. On successful exit (no exception):
#                 #    The status spinner has already stopped/cleared by exiting the 'with' block.
#                 #    Print the final, permanent success message.
#                 self.console.print(f"[green]✔ [COMPLETED][/green] {message}")
#                 self.logger.execute(f"[COMPLETED] {message}")

#             except Exception as e:
#                 # 4. On failure/exception:
#                 #    The status spinner has already stopped/cleared.

#                 # Determine status tag
#                 is_critical = isinstance(e, ShellCommandError) # Check for expected command failure
#                 status_tag = "[CRITICAL]" if is_critical else "[FAILED]"

#                 # Print the final, permanent failure message
#                 self.console.print(f"[bold red]✘ {status_tag}[/bold red] {message}")
#                 self.logger.execute(f"{status_tag} {message}")

#                 # Ensure the exception is logged to file with full traceback
#                 self.logger.exception(f"Exception during execution step: {message}")

#                 # Do NOT show the full Rich traceback for ShellCommandError, as the error
#                 # message itself (printed by the Executor) is usually sufficient.
#                 if not is_critical:
#                     self.console.print("\n[bold red]Traceback (most recent call last):[/bold red]")
#                     self.console.print_exception(show_locals=True)

#                 raise # Re-raise the exception to be handled upstream

#     # --- Standard Logging Wrappers (Ensure status is stopped before printing) ---

#     def info(self, message, *args, **kwargs):
#         self._stop_current_status()
#         self.logger.info(message, *args, **kwargs)

#     def warning(self, message, *args, **kwargs):
#         self._stop_current_status()
#         self.logger.warning(message, *args, **kwargs)

#     def error(self, message, *args, **kwargs):
#         self._stop_current_status()
#         self.logger.error(message, *args, **kwargs)

#     def debug(self, message, *args, **kwargs):
#         self._stop_current_status()
#         self.logger.debug(message, *args, **kwargs)

#     def critical(self, message, *args, **kwargs):
#         self._stop_current_status()
#         self.logger.critical(message, *args, **kwargs)

#     def exception(self, message, *args, **kwargs):
#         """Logs an ERROR to file with traceback and prints a rich traceback to the console."""
#         self._stop_current_status()

#         # 1. Log to file with traceback
#         self.logger.exception(message, *args, **kwargs)

#         # 2. Print Rich traceback to console (useful if exception isn't caught by context manager)
#         self.console.print(f"[bold red]FATAL ERROR: {message}[/bold red]")
#         self.console.print_exception(show_locals=True)

#     def _stop_current_status(self):
#         """Stops the current Rich Status bar and prints a newline if necessary."""
#         # Note: This is now mostly a safety net, as the context manager handles most status stops
#         if self._current_status:
#             self._current_status.stop()
#             self._current_status = None


# # --- 4. Initialization Routine ---
# def initialize_app_logger(
#     app_name: str,
#     log_directory: str = "logs",
#     log_file_name: str = "application.log",
#     file_log_level: int = logging.DEBUG,
#     console_log_level: int = logging.INFO,
# ) -> RichAppLogger:
#     """
#     Initializes and configures the AppLogger for file output and Rich Console for TUI.
#     """
#     # Note: Since logging.setLoggerClass was called, this returns AppLogger instance
#     logger: AppLogger = logging.getLogger(app_name)
#     logger.setLevel(logging.DEBUG) # Lowest level for full file capture
#     logger.propagate = False

#     # Clear existing handlers
#     for handler in logger.handlers[:]:
#         logger.removeHandler(handler)

#     # 1. File Handler Setup
#     os.makedirs(log_directory, exist_ok=True)
#     log_file_path = os.path.join(log_directory, log_file_name)

#     file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
#     file_handler.setLevel(file_log_level)
#     file_formatter = FileFormatter()
#     file_handler.setFormatter(file_formatter)
#     logger.addHandler(file_handler)

#     # 2. Rich Console Setup
#     # Create the console instance
#     console = Console(file=sys.stderr, force_terminal=True, soft_wrap=True)

#     # 3. Rich Handler Setup (For standard logs: INFO, WARNING, ERROR, etc.)
#     # This automatically handles TUI formatting for standard levels
#     stream_handler = RichHandler(
#         console=console,
#         show_time=False, # Time is less useful in TUI than file
#         show_level=True,
#         show_path=False, # Path is verbose for TUI
#         keywords=[], # Prevents Rich from highlighting random words
#         level=console_log_level
#     )
#     # Use the FileFormatter for the stream handler's logging.Formatter base
#     # stream_handler.setFormatter(FileFormatter()) # Optional, generally not needed for RichHandler
#     logger.addHandler(stream_handler)

#     # 4. Instantiate and return the wrapper
#     return RichAppLogger(console, logger)

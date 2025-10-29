# pure-arch/utils/logger.py

"""
This module defines a custom logging solution, AppLogger, which extends Python's
standard logging.Logger. It introduces custom logging levels (SECTION and EXECUTE)
and provides specialized console output handling, including colored messages
and in-place line overwriting for EXECUTE level logs.

It includes:
- Custom log levels: SECTION (for logical application stages) and EXECUTE (for commands/tasks).
- ColoredFormatter: Formats console output with ANSI escape codes for visual distinction.
- FileFormatter: Formats file output with fixed-width fields for readability, without colors.
- AppLogger: A subclass of logging.Logger that implements the custom levels and
  manages direct console output for EXECUTE messages to enable overwriting.
- NoExecuteConsoleFilter: A filter to prevent EXECUTE messages from being processed
  by the StreamHandler, ensuring direct console writing in AppLogger.execute takes precedence.

Notes:
- Initialise in the main() application routine.
- All other modules: logger = logging.getLogger("ArchInstaller")
"""

import logging
import os
import sys

# Define custom logging levels for SECTION and EXECUTE.
# These numerical values are chosen to fit between standard levels (INFO is 20, WARNING is 30).
SECTION_LEVEL_NUM = 25
EXECUTE_LEVEL_NUM = 26

# Register the custom level names with the logging module.
logging.addLevelName(SECTION_LEVEL_NUM, 'SECTION')
logging.addLevelName(EXECUTE_LEVEL_NUM, 'EXECUTE')

class ColoredFormatter(logging.Formatter):
    """
    A custom logging formatter for console output that applies ANSI escape codes
    to color log messages based on their level.

    EXECUTE level messages are intentionally not fully formatted by this class
    for console output; their coloring and line control are handled directly
    by the AppLogger.execute method. This formatter is primarily for other levels
    processed by the StreamHandler.
    """
    COLORS = {
        'CRITICAL': '\033[91m',        # Red
        'ERROR':    '\033[91m',        # Red
        'WARNING':  '\033[38;5;214m',  # Orange (256-color code)
        'SECTION':  '\033[33;7m',      # Yellow
        'EXECUTE':  '\033[92m',        # Green
        'INFO':     '\033[38;5;214m',  # Amber
        'DEBUG':    '\033[94m',        # Blue
        'RESET':    '\033[0m'          # Reset color to default
    }

    def format(self, record):
        """
        Formats a log record by applying a color based on its level and
        resetting the color afterwards. It does not append a newline, as this
        is typically handled by the logging handler itself (e.g., StreamHandler).

        Args:
            record (logging.LogRecord): The log record to format.

        Returns:
            str: The formatted and colored log message.
        """
        level_name = record.levelname
        color = self.COLORS.get(level_name, self.COLORS['RESET'])
        message = super().format(record)

        # Formatter returns the colored message without a newline.
        # The StreamHandler will add the single newline.
        return f"{color}{message}{self.COLORS['RESET']}"


class FileFormatter(logging.Formatter):
    """
    A custom logging formatter for file output. It includes detailed log record
    information (timestamp, level, logger name, file, line number) and the message.
    Fields are formatted with fixed widths to enhance readability in log files.
    Color codes are explicitly excluded from file output.
    """
    def __init__(self, fmt, datefmt=None, style='%'):
        """
        Initializes the FileFormatter with a specific format string.

        Args:
            fmt (str): The format string for the log record.
            datefmt (str, optional): The format string for the date/time field. Defaults to None.
            style (str, optional): The style of the format string ('%', '{', or '$'). Defaults to '%'.
        """
        super().__init__(fmt, datefmt, style)

    def format(self, record):
        """
        Formats a log record for file output, ensuring fixed-width fields for
        levelname, name, filename, and lineno. This method should not include
        any ANSI color escape codes.

        Args:
            record (logging.LogRecord): The log record to format.

        Returns:
            str: The formatted log message suitable for file writing.
        """
        # Add fixed-width attributes to the record for consistent formatting
        record.levelname_fixed = f"{record.levelname:<9}" # e.g., "INFO     "
        record.name_fixed = f"{record.name:<15}"         # e.g., "my_logger      "
        record.filename_fixed = f"{record.filename:<20}" # e.g., "my_module.py        "
        record.lineno_fixed = f"{record.lineno:<5}"      # e.g., "123  "

        return super().format(record)


class AppLogger(logging.Logger):
    """
    A specialized Logger class that extends `logging.Logger` to incorporate
    custom logging levels and unique console output behavior for 'EXECUTE' messages.

    Key features:
    - Custom 'SECTION' level for marking distinct stages of application execution.
    - Custom 'EXECUTE' level for displaying ongoing operations with real-time
      overwrite capabilities on the console ([EXECUTING], [COMPLETED], [FAILED]).
    - Ensures that any pending 'EXECUTE' line on the console is completed with a
      newline before other log messages are printed to maintain clean output.
    """
    def __init__(self, name, level=logging.NOTSET):
        """
        Initializes the AppLogger instance.

        Args:
            name (str): The name of the logger.
            level (int, optional): The initial logging level. Defaults to logging.NOTSET.
        """
        super().__init__(name, level)
        # Prevent propagation to ancestor loggers (e.g., the root logger)
        # to ensure only explicitly added handlers process messages.
        self.propagate = False
        # Flag to track if an EXECUTE message is currently displayed on the console
        # without a trailing newline, awaiting a completion message or a newline.
        self._last_execute_is_pending = False

    def section(self, message, *args, **kwargs):
        """
        Logs a message with the custom SECTION level.
        Typically used to indicate the start of a major application phase.

        Args:
            message (str): The log message string.
            *args: Variable positional arguments to be merged into the message.
            **kwargs: Keyword arguments, often used for `exc_info`, `stack_info`, etc.
        """
        self._ensure_execute_line_completed() # Ensure previous EXECUTE line is finished
        if self.isEnabledFor(SECTION_LEVEL_NUM):
            self._log(SECTION_LEVEL_NUM, message, args, **kwargs)

    def execute(self, message, success=None, *args, **kwargs):
        """
        Logs a message with the custom EXECUTE level. This method provides special
        console behavior for real-time feedback on tasks.

        - When `success` is None (initial call): Displays "[EXECUTING] message"
          on the console, without a newline, allowing subsequent overwriting.
        - When `success` is True: Displays "[COMPLETED] message" (in green)
          on the console, overwriting the previous line, and adds a newline.
        - When `success` is False: Displays "[FAILED] message" (in red)
          on the console, overwriting the previous line, and adds a newline.

        EXECUTE messages are written directly to `sys.stdout` for precise cursor
        control on the console and are sent separately to the file handler.

        Args:
            message (str): The log message string describing the task/command.
            success (bool, optional): Indicates the success/failure of the task.
                                       None for initial 'executing' state.
                                       True for 'completed' state.
                                       False for 'failed' state. Defaults to None.
            *args: Variable positional arguments for message formatting (ignored for console,
                   passed to file log if message contains format specifiers).
            **kwargs: Keyword arguments for the log record (e.g., `exc_info` for file log).
        """
        if self.isEnabledFor(EXECUTE_LEVEL_NUM):
            console_message_str = ""
            file_message_str = ""

            # Get color from ColoredFormatter.COLORS
            execute_color = ColoredFormatter.COLORS['EXECUTE']
            fail_color = ColoredFormatter.COLORS['CRITICAL']

            if success is True:
                console_message_str = f"\r{execute_color}[COMPLETED] {message}{ColoredFormatter.COLORS['RESET']}\033[K\n"
                file_message_str = f"[COMPLETED] {message}"
                self._last_execute_is_pending = False # Task completed
            elif success is False:
                console_message_str = f"\r{fail_color}[FAILED] {message}{ColoredFormatter.COLORS['RESET']}\033[K\n"
                file_message_str = f"[FAILED] {message}"
                self._last_execute_is_pending = False # Task failed
            else: # success is None, initial call
                # \r: Carriage return to move cursor to start of line.
                # No \n: Prevents a newline, keeping the cursor on the same line for overwriting.
                console_message_str = f"\r{execute_color}[EXECUTING] {message}{ColoredFormatter.COLORS['RESET']}"
                file_message_str = f"[EXECUTING] {message}"
                self._last_execute_is_pending = True # Mark as pending

            # Write directly to standard output stream for immediate, precise control.
            sys.stdout.write(console_message_str)
            sys.stdout.flush() # Ensure message is displayed immediately

            # Manually create and emit a LogRecord to the FileHandler.
            # This bypasses the StreamHandler (due to NoExecuteConsoleFilter)
            # ensuring EXECUTE messages don't get double-processed for console.

            # --- CRITICAL FIX: Use slice to unpack only the first three elements ---
            caller_info = self.findCaller(stack_info=False)
            file_name, line_no, func_name = caller_info[:3]

            record = self.makeRecord(
                self.name, EXECUTE_LEVEL_NUM,
                file_name, line_no, # Source file and line number
                file_message_str, (), # Message string and empty tuple for args
                exc_info=None, func=func_name, extra=kwargs # Exception info, function name, and extra data
            )
            # Iterate through handlers and emit only to FileHandler instances
            for handler in self.handlers:
                if isinstance(handler, logging.FileHandler):
                    handler.emit(record)


    def _ensure_execute_line_completed(self):
        """
        Internal helper method. If the last console output was an 'EXECUTE'
        message that is still pending (i.e., it didn't end with a newline),
        this method prints a newline to `sys.stdout` to complete that line.
        This prevents subsequent non-EXECUTE log messages from appearing on
        the same line as an uncompleted EXECUTE message.
        """
        if self._last_execute_is_pending:
            sys.stdout.write("\n") # Add a newline to terminate the previous EXECUTE line
            sys.stdout.flush()     # Ensure the newline is displayed immediately
            self._last_execute_is_pending = False # Reset the pending flag

    # Override standard logging methods to integrate `_ensure_execute_line_completed`.
    # This ensures that any pending EXECUTE line is finalized before a new log message
    # from these standard levels is displayed, maintaining clean console output.

    def critical(self, message, *args, **kwargs):
        """Logs a message with the CRITICAL level."""
        self._ensure_execute_line_completed()
        super().critical(message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        """Logs a message with the ERROR level."""
        self._ensure_execute_line_completed()
        super().error(message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        """Logs a message with the WARNING level."""
        self._ensure_execute_line_completed()
        super().warning(message, *args, **kwargs)

    def info(self, message, *args, **kwargs):
        """Logs a message with the INFO level."""
        self._ensure_execute_line_completed()
        super().info(message, *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        """Logs a message with the DEBUG level."""
        self._ensure_execute_line_completed()
        super().debug(message, *args, **kwargs)

# Register AppLogger as the default logger class to be used when logging.getLogger() is called.
logging.setLoggerClass(AppLogger)

# --- Define a filter to prevent EXECUTE messages from reaching the StreamHandler ---
class NoExecuteConsoleFilter(logging.Filter):
    """
    A logging filter specifically designed to prevent LogRecords with the
    EXECUTE level from being processed by a handler.

    This is crucial for the AppLogger's functionality, as EXECUTE messages
    for console output are handled directly by `AppLogger.execute` using
    `sys.stdout.write` for precise line control and overwriting.
    """
    def filter(self, record):
        """
        Determines if the given log record should be processed by the handler.

        Args:
            record (logging.LogRecord): The log record to check.

        Returns:
            bool: True if the record should be processed, False otherwise.
        """
        return record.levelno != EXECUTE_LEVEL_NUM


def initialize_app_logger(
    app_name: str,
    log_directory: str = "logs",
    log_file_name: str = "application.log",
    console_log_level: int = logging.INFO,
    file_log_level: int = logging.DEBUG,
    enable_console_logging: bool = True,
    enable_file_logging: bool = True
) -> AppLogger:
    """
    Initializes and configures the AppLogger for a large application.

    This routine sets up:
    - A custom AppLogger instance for the application's root logger.
    - A StreamHandler for console output (with colors and EXECUTE overwrite behavior).
    - A FileHandler for comprehensive file logging (uncolored, detailed).
    - Ensures proper handling of custom log levels and prevents duplicate console output.

    Args:
        app_name (str): The name of the application. This will be used as the logger's name.
        log_directory (str): The directory where log files will be stored. Defaults to "logs".
        log_file_name (str): The name of the main log file. Defaults to "application.log".
        console_log_level (int): The minimum logging level for console output.
                                 Common choices: logging.INFO, logging.DEBUG.
        file_log_level (int): The minimum logging level for file output.
                              Common choices: logging.DEBUG (most verbose), logging.INFO.
        enable_console_logging (bool): If True, console output will be enabled.
        enable_file_logging (bool): If True, file logging will be enabled.

    Returns:
        AppLogger: The configured AppLogger instance for the application.
    """
    try:
        # Ensure AppLogger is set as the default logger class for this application's loggers.
        # This only needs to be called once per application run.
        if not isinstance(logging.getLoggerClass(), type(AppLogger)):
            logging.setLoggerClass(AppLogger)

        # Get the root logger for the application.
        # Using the provided app_name ensures distinct loggers if needed for sub-modules.
        logger = logging.getLogger(app_name)

        # Set the lowest level for the logger itself. This ensures all messages
        # are captured by the logger before being filtered by individual handlers.
        logger.setLevel(logging.DEBUG)

        # Clear existing handlers to prevent duplicate output if this function
        # is called multiple times (e.g., during testing or re-initialization).
        for handler in logger.handlers[:]: # Iterate over a slice to safely remove
            logger.removeHandler(handler)

        # --- Console Handler Setup ---
        if enable_console_logging:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(console_log_level)

            # Use ColoredFormatter for console output.
            # Format: LEVELNAME: MESSAGE
            console_formatter = ColoredFormatter('%(levelname)s: %(message)s')
            console_handler.setFormatter(console_formatter)

            # Add the filter to prevent EXECUTE messages from being processed by StreamHandler.
            # EXECUTE messages are handled directly by AppLogger.execute for overwriting.
            console_handler.addFilter(NoExecuteConsoleFilter())

            logger.addHandler(console_handler)

        # --- File Handler Setup ---
        if enable_file_logging:
            # Create log directory if it doesn't exist.
            os.makedirs(log_directory, exist_ok=True)
            log_file_path = os.path.join(log_directory, log_file_name)

            file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
            file_handler.setLevel(file_log_level)

            # Use FileFormatter for detailed, uncolored file output.
            # Format: TIMESTAMP - LEVEL - LOGGER_NAME - FILENAME:LINENO - MESSAGE
            file_formatter = FileFormatter(
                '%(asctime)s - %(levelname_fixed)s - %(name_fixed)s - %(filename_fixed)s:%(lineno_fixed)s - %(message)s'
            )
            file_handler.setFormatter(file_formatter)

            logger.addHandler(file_handler)

        return logger

    except Exception as e:
        # Fallback error handling: if logger initialization fails,
        # print an error to stderr and return a basic logger.
        # This prevents the application from crashing due to logging setup issues.
        print(f"ERROR: Failed to initialize application logger: {e}", file=sys.stderr)
        # Return a standard Python logger as a fallback.
        return logging.getLogger(app_name)

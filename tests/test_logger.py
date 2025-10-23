import logging
import os
import sys
import pytest
from unittest.mock import MagicMock, patch, call
from io import StringIO
import re

# Assuming the refactored code is in 'pure_arch/utils/logger.py'
# NOTE: Ensure your test runner can resolve this import path.
from pure_arch.utils.logger import (
    initialize_app_logger,
    AppLogger,
    RichAppLogger
)

# --- Helper Function for Stripping ANSI (Useful for general string content checking) ---

def strip_ansi(text):
    """Strips all ANSI escape codes from a string."""
    # This regex removes most common ANSI control sequences
    return re.sub(r'\x1b\[.*?m', '', text)

# --- Fixtures for Testing ---

@pytest.fixture(scope="function")
def cleanup_logging_state():
    """Fixture to reset the logging state before and after each test."""
    # Ensure our custom logger class is used
    logging.setLoggerClass(AppLogger)

    # Clear handlers from all loggers to ensure isolation
    for logger_name in list(logging.root.manager.loggerDict.keys()):
        logger = logging.getLogger(logger_name)
        logger.handlers = []

    yield

    # Post-test cleanup (resetting handlers again)
    for logger_name in list(logging.root.manager.loggerDict.keys()):
        logger = logging.getLogger(logger_name)
        logger.handlers = []


@pytest.fixture(scope="function")
def mock_rich_logger(tmp_path, cleanup_logging_state):
    """
    Initializes RichAppLogger, uses a temporary log directory,
    and returns the wrapper instance and directory path.
    """
    log_dir = tmp_path / "logs"

    logger_wrapper = initialize_app_logger(
        app_name="TestApp",
        log_directory=str(log_dir),
        log_file_name="test.log",
        file_log_level=logging.DEBUG
    )

    yield logger_wrapper, log_dir


# --- Helper Functions ---

def get_file_content(log_dir, filename="test.log"):
    """Reads the content of the log file."""
    log_path = log_dir / filename
    if log_path.exists():
        with open(log_path, 'r', encoding='utf-8') as f:
            return f.read()
    return ""


# --- Tests ---

def test_initialization_and_configuration(mock_rich_logger):
    """Tests if initialization correctly sets up the logger and handlers."""
    logger_wrapper, log_dir = mock_rich_logger

    assert isinstance(logger_wrapper, RichAppLogger)
    assert isinstance(logger_wrapper.logger, AppLogger)
    assert log_dir.is_dir()

    handlers = logger_wrapper.logger.handlers
    assert len(handlers) == 2
    assert any(isinstance(h, logging.FileHandler) for h in handlers)
    # Check for the RichHandler which is a StreamHandler subclass
    assert any("RichHandler" in h.__class__.__name__ for h in handlers)


@patch('pure_arch.utils.logger.RichAppLogger._stop_current_status')
def test_standard_logging_to_file(mock_stop_status, mock_rich_logger):
    """Tests standard log levels (INFO, ERROR) successfully write to the file."""
    logger_wrapper, log_dir = mock_rich_logger

    logger_wrapper.info("Standard information message.")
    logger_wrapper.error("An application error.")

    # Check File Content
    file_content = get_file_content(log_dir)
    assert "Standard information message." in file_content
    assert "An application error." in file_content

    # Check internal calls
    assert mock_stop_status.call_count == 2


def test_execution_step_success(mock_rich_logger):
    """Tests the execution_step context manager on success."""
    logger_wrapper, log_dir = mock_rich_logger
    step_message = "Running a task successfully"

    # Patch the console methods on the *instance's* console attribute
    with patch.object(logger_wrapper.console, 'status') as mock_status, \
         patch.object(logger_wrapper.console, 'print') as mock_console_print:

        mock_spinner = MagicMock()
        mock_status.return_value.__enter__.return_value = mock_spinner

        with logger_wrapper.execution_step(step_message):
            pass

        # 1. Check TUI Print
        mock_console_print.assert_any_call(
            f"[green]✔ [COMPLETED][/green] {step_message}"
        )

    # 2. Check File Content (Outside the patches)
    file_content = get_file_content(log_dir)
    assert f"[EXECUTING] {step_message}" in file_content
    assert f"[COMPLETED] {step_message}" in file_content

    # 3. Check Rich Status Calls
    mock_status.assert_called_once()


def test_execution_step_failure(mock_rich_logger):
    """Tests the execution_step context manager on failure (exception)."""
    logger_wrapper, log_dir = mock_rich_logger
    step_message = "Running a task that fails"

    # Patch the console methods on the *instance's* console attribute
    with patch.object(logger_wrapper.console, 'status') as mock_status, \
         patch.object(logger_wrapper.console, 'print') as mock_console_print, \
         patch.object(logger_wrapper.console, 'print_exception') as mock_print_exception:

        mock_spinner = MagicMock()
        mock_status.return_value.__enter__.return_value = mock_spinner

        with pytest.raises(ValueError):
            with logger_wrapper.execution_step(step_message):
                raise ValueError("Something went wrong.")

        # 1. Check TUI Prints
        mock_console_print.assert_has_calls([
            call(f"[bold red]✘ [FAILED][/bold red] {step_message}"),
            call("\n[bold red]Traceback (most recent call last):[/bold red]"),
        ], any_order=True)

        # 2. Check Rich Traceback Call
        mock_print_exception.assert_called_once_with(show_locals=True)

    # 3. Check File Content (Outside the patches)
    file_content = get_file_content(log_dir)
    assert f"[EXECUTING] {step_message}" in file_content
    assert f"[FAILED] {step_message}" in file_content
    assert "ValueError: Something went wrong." in file_content


@patch('pure_arch.utils.logger.RichAppLogger._stop_current_status')
def test_exception_method(mock_stop_status, mock_rich_logger):
    """Tests the explicit exception() method for logging and TUI traceback."""
    logger_wrapper, log_dir = mock_rich_logger

    # Patch the console methods on the *instance's* console attribute
    with patch.object(logger_wrapper.console, 'print') as mock_console_print, \
         patch.object(logger_wrapper.console, 'print_exception') as mock_print_exception:

        try:
            raise RuntimeError("External system failure")
        except RuntimeError:
            logger_wrapper.exception("Caught an unhandled error.")

        # 1. Check TUI Prints
        mock_console_print.assert_any_call(
            "[bold red]FATAL ERROR: Caught an unhandled error.[/bold red]"
        )

        # 2. Check Rich Traceback Call
        mock_print_exception.assert_called_once_with(show_locals=True)

    # 3. Check File Content (Outside the patches)
    file_content = get_file_content(log_dir)
    assert "ERROR" in file_content
    assert "Caught an unhandled error." in file_content

    # 4. Check internal calls
    mock_stop_status.assert_called_once()

@pytest.fixture(scope="function")
def isolated_rich_logger(tmp_path, cleanup_logging_state):
    """
    Initializes RichAppLogger, but removes the RichHandler
    to ensure only custom TUI prints are captured.
    """
    log_dir = tmp_path / "logs"

    # Initialize normally
    logger_wrapper = initialize_app_logger(
        app_name="IsolatedApp",
        log_directory=str(log_dir),
        log_file_name="isolated.log",
        file_log_level=logging.DEBUG
    )

    # ISOLATION STEP: Remove the RichHandler (StreamHandler)
    for handler in logger_wrapper.logger.handlers[:]:
        if "RichHandler" in handler.__class__.__name__:
            logger_wrapper.logger.removeHandler(handler)
            break

    yield logger_wrapper, log_dir


@patch('pure_arch.utils.logger.RichAppLogger._stop_current_status')
def test_section_logging(mock_stop_status, isolated_rich_logger): # <-- Use the isolated fixture
    """Tests section() calls the correct logging method and prints the TUI header."""
    logger_wrapper, log_dir = isolated_rich_logger
    section_message = "Starting a new phase."

    # Patch the console.print method on the *instance's* console attribute
    with patch.object(logger_wrapper.console, 'print') as mock_console_print:
        logger_wrapper.section(section_message)

    # 1. Check File Content
    file_content = get_file_content(log_dir, filename="isolated.log") # Use isolated filename
    assert "SECTION: Starting a new phase." in file_content

    # --- FIX: Now we expect exactly ONE print call ---
    mock_console_print.assert_called_once()

    # 2. Verify *your* custom print call was correct
    # The call_args_list will have one item: call_arg = (args, kwargs)
    printed_arg = str(mock_console_print.call_args[0][0])
    assert f"SECTION: {section_message}" in printed_arg

    # 3. Check internal calls
    mock_stop_status.assert_called_once()

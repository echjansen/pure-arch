import pytest
import subprocess
from unittest.mock import MagicMock, patch, call
import shlex
import logging

# Assuming the structure:
# pure_arch/utils/executor.py
# pure_arch/utils/logger.py
from pure_arch.utils.executor import Executor, ShellCommandError, CommandTimeoutError, CommandNotFoundError, PermissionDeniedError, InvalidCommandError
from pure_arch.utils.logger import RichAppLogger # Import the logger class used for type-hinting

# --- Fixtures ---

@pytest.fixture
def mock_rich_logger():
    """Provides a fully-mocked RichAppLogger instance for dependency injection."""
    mock_logger = MagicMock(spec=RichAppLogger)

    # Configure the mock to return a context manager for execution_step
    mock_context_manager = MagicMock()
    mock_context_manager.__enter__.return_value = None
    mock_context_manager.__exit__.return_value = None # Ensure it doesn't suppress exceptions
    mock_logger.execution_step.return_value = mock_context_manager

    return mock_logger

@pytest.fixture
def executor(mock_rich_logger):
    """Provides an Executor instance with the mocked logger injected."""
    return Executor(logger_instance=mock_rich_logger, default_timeout=5.0)

# --- Test Helper Classes/Mocks ---

class MockCompletedProcess:
    """A mock object to simulate the return value of subprocess.run."""
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.args = []

# --- Tests for Initialization and Setup ---

def test_executor_initialization(mock_rich_logger):
    """Tests if the Executor initializes correctly and stores the logger."""
    exec_instance = Executor(logger_instance=mock_rich_logger, default_timeout=10.0, chroot_path="/mnt/target")
    assert exec_instance._default_timeout == 10.0
    assert exec_instance._chroot_path == "/mnt/target"
    assert exec_instance.logger == mock_rich_logger
    mock_rich_logger.debug.assert_called()

def test_executor_initialization_invalid_timeout(mock_rich_logger):
    """Tests if initialization raises ValueError for invalid timeout."""
    with pytest.raises(ValueError, match="positive number"):
        Executor(logger_instance=mock_rich_logger, default_timeout=-1)

# --- Tests for _prepare_command ---

def test_prepare_command_list(executor):
    """Tests preparation of a list command without chroot."""
    cmd = ["ls", "-l"]
    prepared = executor._prepare_command(cmd, chroot=False)
    assert prepared == ["ls", "-l"]

def test_prepare_command_string_no_chroot(executor):
    """Tests preparation of a string command without chroot."""
    cmd = "pacman -Syu --noconfirm"
    prepared = executor._prepare_command(cmd, chroot=False)
    assert prepared == ["pacman", "-Syu", "--noconfirm"]

def test_prepare_command_string_with_chroot(executor):
    """Tests preparation of a string command with chroot prepended."""
    cmd = "ls /etc/pacman.conf"
    executor._chroot_path = "/newroot"
    prepared = executor._prepare_command(cmd, chroot=True)
    assert prepared == ["arch-chroot", "/newroot", "ls", "/etc/pacman.conf"]

def test_prepare_command_invalid_input(executor):
    """Tests that InvalidCommandError is raised for invalid input."""
    with pytest.raises(InvalidCommandError):
        executor._prepare_command("", chroot=False)
    with pytest.raises(InvalidCommandError):
        executor._prepare_command(None, chroot=False)
    with pytest.raises(InvalidCommandError):
        executor._prepare_command(["ls", 123], chroot=False)

# --- Tests for execute_command (Low-level) ---

@patch('subprocess.run')
def test_execute_command_success(mock_run, executor):
    """Tests successful command execution (exit code 0)."""
    mock_run.return_value = MockCompletedProcess(
        returncode=0,
        stdout="disk found",
        stderr=""
    )

    cmd = ["fdisk", "-l"]
    exit_code, stdout, stderr = executor.execute_command(cmd, check=True)

    mock_run.assert_called_once()
    assert exit_code == 0
    assert stdout == "disk found"
    assert stderr == ""

@patch('subprocess.run')
def test_execute_command_error_no_check(mock_run, executor):
    """Tests command failure when 'check' is False (no exception raised)."""
    mock_run.return_value = MockCompletedProcess(
        returncode=1,
        stdout="",
        stderr="Minor error"
    )

    cmd = ["bad_command"]
    exit_code, stdout, stderr = executor.execute_command(cmd, check=False)

    assert exit_code == 1
    assert stderr == "Minor error"
    executor.logger.error.assert_not_called()

@patch('subprocess.run')
def test_execute_command_error_shellcommanderror(mock_run, executor):
    """Tests command failure when 'check' is True (raises ShellCommandError)."""
    mock_run.return_value = MockCompletedProcess(
        returncode=5,
        stdout="Some output",
        stderr="Unknown failure"
    )

    cmd = ["fdisk", "-l"]
    with pytest.raises(ShellCommandError) as excinfo:
        executor.execute_command(cmd, check=True)

    assert excinfo.value.exit_code == 5
    executor.logger.error.assert_called_once()

@patch('subprocess.run')
def test_execute_command_command_not_found_error(mock_run, executor):
    """Tests CommandNotFoundError detection via stderr string."""
    mock_run.return_value = MockCompletedProcess(
        returncode=127,
        stdout="",
        stderr="bash: my_command: command not found"
    )

    with pytest.raises(CommandNotFoundError):
        executor.execute_command("my_command", check=True)

@patch('subprocess.run', side_effect=subprocess.TimeoutExpired(cmd=["test"], timeout=5.0, output=b'', stderr=b''))
def test_execute_command_timeout_error(mock_run, executor):
    """Tests CommandTimeoutError when subprocess.TimeoutExpired is raised."""
    cmd = ["long_running_script"]
    with pytest.raises(CommandTimeoutError) as excinfo:
        executor.execute_command(cmd, timeout=5.0)

    assert "timed out" in str(excinfo.value)
    executor.logger.warning.assert_called_once()

# --- Tests for run() (High-level) ---

@patch.object(Executor, 'execute_command')
def test_run_success(mock_execute_command, executor, mock_rich_logger):
    """Tests the high-level run() method on successful command execution."""
    mock_execute_command.return_value = (0, "Success!", "")

    description = "Test success"
    cmd = "test_cmd"

    exit_code, stdout, stderr = executor.run(description, cmd)

    # 1. Check return values
    assert exit_code == 0
    assert stdout == "Success!"

    # 2. Check low-level call arguments (should be prepared list)
    mock_execute_command.assert_called_once_with(
        command=['test_cmd'], # Should be shlex.split'd
        capture_output=True,
        timeout=None,
        check=True,
        shell=False,
        cwd=None
    )

    # 3. Check TUI/Logger interaction
    mock_rich_logger.execution_step.assert_called_once_with(description)
    # Check that the success path log (debug of output) was hit
    mock_rich_logger.debug.assert_called()

@patch.object(Executor, 'execute_command')
def test_run_failure(mock_execute_command, executor, mock_rich_logger):
    """Tests the high-level run() method on command execution failure."""
    # Configure the low-level method to fail
    mock_execute_command.side_effect = ShellCommandError(
        command="test_cmd", exit_code=1, stderr="Permission denied."
    )

    description = "Test failure"
    cmd = "test_cmd"

    with pytest.raises(ShellCommandError):
        executor.run(description, cmd)

    # 1. Check low-level call arguments
    mock_execute_command.assert_called_once()

    # 2. Check TUI/Logger interaction
    mock_rich_logger.execution_step.assert_called_once_with(description)
    # The execution_step context manager *exited* with an exception, causing the failure logs
    mock_rich_logger.error.assert_called_once()
    mock_rich_logger.exception.assert_not_called() # exception() is called inside the context manager, not here.

@patch.object(Executor, 'execute_command')
def test_run_dryrun(mock_execute_command, executor, mock_rich_logger):
    """Tests the dry-run feature."""
    description = "Test dryrun"
    cmd = "format /dev/sda"

    exit_code, stdout, stderr = executor.run(description, cmd, dryrun=True)

    # 1. Check return values
    assert exit_code == 0
    assert stdout == "DRY_RUN_STDOUT"

    # 2. Check that execute_command was NOT called
    mock_execute_command.assert_not_called()

    # 3. Check Logger interaction
    mock_rich_logger.info.assert_called_with(
        "DRY RUN: Execution skipped for: 'Test dryrun'"
    )
    # execution_step should NOT be called during dry-run
    mock_rich_logger.execution_step.assert_not_called()

@patch.object(Executor, 'execute_command')
def test_run_with_chroot(mock_execute_command, executor, mock_rich_logger):
    """Tests that the command passed to the low-level executor includes arch-chroot when requested."""
    mock_execute_command.return_value = (0, "", "")

    executor._chroot_path = "/mnt/arch"
    cmd = "pacman -S base"

    executor.run("Install base system", cmd, chroot=True)

    # The command passed to execute_command must be the fully prepared list
    expected_command = shlex.split(f"arch-chroot {executor._chroot_path} {cmd}")

    mock_execute_command.assert_called_once()
    # Check that the first argument (command) matches the expected chroot command
    assert mock_execute_command.call_args[0][0] == expected_command

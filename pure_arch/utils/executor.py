# pure_arch/utils/executor.py

import subprocess
import shlex
from typing import Tuple, Optional, Union, List

# Local imports
from .. import core
from pure_arch.utils.logger import initialize_app_logger, RichAppLogger
# NOTE: We keep initialize_app_logger for the fallback logger setup

# --- 0. Custom Executor Exceptions ---


class ShellCommandError(Exception):
    """Base class for errors related to shell command execution."""

    def __init__(self, command: str, exit_code: int = -1, stdout: str = "", stderr: str = "", message: str = "Command execution failed."):
        self.command = command
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(f"{message} (Command: '{command}', Exit Code: {exit_code})")


class CommandNotFoundError(ShellCommandError):
    """Raised when the executable specified in the command cannot be found."""

    def __init__(self, command: str, stdout: str = "", stderr: str = ""):
        super().__init__(command, exit_code=127, stdout=stdout, stderr=stderr, message="Command not found.")


class CommandTimeoutError(ShellCommandError):
    """Raised when the command exceeds the execution timeout."""

    def __init__(self, command: str, timeout: float, stdout: str = "", stderr: str = ""):
        self.timeout = timeout
        super().__init__(command, exit_code=124, stdout=stdout, stderr=stderr, message=f"Command timed out after {timeout} seconds.")


class InvalidCommandError(ShellCommandError):
    """Raised when the command string/list is invalid, empty, or improperly formatted."""

    def __init__(self, command: str, message: str):
        super().__init__(command, exit_code=-2, message=message)


class PermissionDeniedError(ShellCommandError):
    """Raised when command execution fails due to permissions."""
    def __init__(self, command: str, stdout: str = "", stderr: str = ""):
        super().__init__(command, exit_code=126, stdout=stdout, stderr=stderr, message="Permission denied.")


# --- Logger Fallback Setup ---

# Provide a fallback logger instance if core.app_logger hasn't been initialized yet.
# Note: This is a robust approach, but the Executor class itself will use self.logger.
_FALLBACK_LOGGER = core.app_logger
if _FALLBACK_LOGGER is None:
    _FALLBACK_LOGGER = initialize_app_logger(app_name="ExecutorFallback")


class Executor:
    """
    A robust class for executing shell commands, using Dependency Injection for logging,
    chroot support, and centralized exception handling via the RichAppLogger.
    """

    def __init__(self,
                 logger_instance: RichAppLogger, # <-- Dependency Injection
                 default_timeout: Optional[float] = 30.0,
                 chroot_path: str = "/mnt"):
        """
        Initializes the Executor.
        """
        self.logger = logger_instance # Store the injected logger instance

        if default_timeout is not None and default_timeout <= 0:
            self.logger.error("Default timeout must be a positive number or None.")
            raise ValueError("Default timeout must be a positive number or None.")
        if not isinstance(chroot_path, str) or not chroot_path:
            self.logger.error("Chroot path must be a non-empty string.")
            raise ValueError("Chroot path must be a non-empty string.")

        self._default_timeout = default_timeout
        self._chroot_path = chroot_path
        self.logger.debug(f"Executor initialized with default_timeout: {self._default_timeout}, chroot_path: {self._chroot_path}")

    def _prepare_command(self, command: Union[str, list], chroot: bool) -> List[str]:
        """
        Prepares the command for execution by shlex.split if it's a string,
        and prepends arch-chroot if chroot is True.
        """
        if not command:
            self.logger.error("Attempted to prepare an empty command.")
            raise InvalidCommandError(str(command), "Command cannot be empty.")

        if isinstance(command, str):
            try:
                parsed_command = shlex.split(command)
            except ValueError as e:
                self.logger.error(f"Failed to parse command string '{command}': {e}")
                raise InvalidCommandError(command, f"Failed to parse command string: {e}")
        elif isinstance(command, list):
            if not all(isinstance(arg, str) for arg in command):
                raise InvalidCommandError(str(command), "All elements in command list must be strings.")
            parsed_command = command
        else:
            self.logger.error(f"Invalid command type: {type(command)}. Expected str or list.")
            raise InvalidCommandError(str(command), "Command must be a string or a list of strings.")

        if chroot:
            return ["arch-chroot", self._chroot_path] + parsed_command
        return parsed_command

    def execute_command(self,
                        command: Union[str, list],
                        capture_output: bool = True,
                        timeout: Optional[float] = None,
                        check: bool = True,
                        shell: bool = False,
                        cwd: Optional[str] = None
                        ) -> Tuple[int, str, str]:
        """
        Executes a shell command using subprocess.run. This is the low-level execution method.
        """
        actual_timeout = timeout if timeout is not None else self._default_timeout
        cmd_string_for_log = shlex.join(command) if isinstance(command, list) else command

        self.logger.debug(f"Attempting low-level execution: '{cmd_string_for_log}' "
                             f"timeout={actual_timeout}s, capture_output={capture_output}, check={check}, shell={shell}")

        try:
            if shell:
                command_to_execute = shlex.join(command) if isinstance(command, list) else command
            else:
                # Re-validate/prepare if string was passed
                if isinstance(command, str):
                    command_to_execute = self._prepare_command(command, chroot=False)
                else:
                    command_to_execute = command

            process = subprocess.run(
                command_to_execute,
                capture_output=capture_output,
                text=True,
                timeout=actual_timeout,
                check=False,
                shell=shell,
                cwd=cwd
            )

            stdout = process.stdout if capture_output and process.stdout else ""
            stderr = process.stderr if capture_output and process.stderr else ""
            exit_code = process.returncode

            if check and exit_code != 0:
                error_message = f"Command failed with exit code {exit_code}"
                self.logger.error(f"Command: '{cmd_string_for_log}', Exit Code: {exit_code}, Stderr: {stderr.strip()}")

                if "command not found" in stderr.lower() or "no such file or directory" in stderr.lower() or exit_code == 127:
                    raise CommandNotFoundError(command=cmd_string_for_log, stdout=stdout, stderr=stderr)
                elif "permission denied" in stderr.lower() or exit_code == 126:
                    raise PermissionDeniedError(command=cmd_string_for_log, stdout=stdout, stderr=stderr)
                else:
                    raise ShellCommandError(
                        command=cmd_string_for_log,
                        exit_code=exit_code,
                        stdout=stdout,
                        stderr=stderr,
                        message=error_message
                    )

            self.logger.debug(f"Low-level execution of '{cmd_string_for_log}' completed with exit code {exit_code}")
            return exit_code, stdout, stderr

        except FileNotFoundError:
            self.logger.error(f"Command '{cmd_string_for_log}' not found. Ensure it's in the system's PATH.")
            raise CommandNotFoundError(command=cmd_string_for_log, stdout="", stderr="Command not found. Check PATH.")
        except subprocess.TimeoutExpired as e:
            self.logger.warning(f"Command '{cmd_string_for_log}' timed out after {actual_timeout} seconds.")
            stdout = e.stdout.decode() if e.stdout else ""
            stderr = e.stderr.decode() if e.stderr else ""
            raise CommandTimeoutError(command=cmd_string_for_log, timeout=actual_timeout, stdout=stdout, stderr=stderr)
        except (TypeError, ValueError) as e:
            self.logger.error(f"Argument error during low-level command execution '{cmd_string_for_log}': {e}")
            raise InvalidCommandError(cmd_string_for_log, f"Argument error in command execution: {e}")
        except Exception as e:
            self.logger.critical(f"An unhandled exception occurred during low-level execution of '{cmd_string_for_log}': {e}", exc_info=True)
            raise ShellCommandError(cmd_string_for_log, -1, "", "", f"An unexpected error occurred: {e}")

    # def run(self,
    #         description: str,
    #         command: Union[str, list],
    #         chroot: bool = False,
    #         dryrun: bool = False,
    #         capture_output: bool = True,
    #         timeout: Optional[float] = None,
    #         check: bool = True,
    #         shell: bool = False,
    #         cwd: Optional[str] = None
    #         ) -> Tuple[int, str, str]:
    #     """
    #     Executes a shell command using the RichAppLogger's execution_step context manager
    #     for enhanced TUI feedback, logging, and centralized exception handling.
    #     """
    #     original_command_str = shlex.join(command) if isinstance(command, list) else command

    #     # Prepare the command list (handles shlex.split and arch-chroot prepending)
    #     prepared_command_list = self._prepare_command(command, chroot=chroot)

    #     #self.logger.info(f"Command to execute: {original_command_str}")

    #     if dryrun:
    #         self.logger.info(f"DRY RUN: Execution skipped for: '{description}'")
    #         self.logger.debug(f"DRY RUN COMMAND (Prepared): {shlex.join(prepared_command_list)}")
    #         return 0, "DRY_RUN_STDOUT", "DRY_RUN_STDERR"

    #     # --- CORE LOGIC: Use logger.execution_step for TUI/Logging ---
    #     try:
    #         with self.logger.execution_step(description):

    #             # Command passed to execute_command depends on the 'shell' flag
    #             cmd_to_pass = prepared_command_list if not shell else original_command_str

    #             exit_code, stdout, stderr = self.execute_command(
    #                 command=cmd_to_pass,
    #                 capture_output=capture_output,
    #                 timeout=timeout,
    #                 check=check,
    #                 shell=shell,
    #                 cwd=cwd
    #             )

    #         # Success Path: Log captured output at DEBUG level after TUI success is shown
    #         self.logger.debug(f"Command '{description}' successfully completed. Output details:")
    #         if stdout:
    #             self.logger.debug(f"  Stdout:\n{stdout.strip()}")
    #         if stderr:
    #             self.logger.debug(f"  Stderr:\n{stderr.strip()}")

    #         return exit_code, stdout, stderr

    #     except ShellCommandError as e:
    #         # Failure Path: execution_step handles TUI printing and file logging (exception).
    #         # We only re-raise the specific, enhanced exception.
    #         self.logger.error(f"Execution failed for '{description}'. Reason: {e.args[0]}")
    #         raise e

    #     except Exception as e:
    #         # Catch unexpected errors. execution_step's internal handler will log and print TUI traceback.
    #         self.logger.critical(f"An unexpected error occurred during run() for '{description}': {e}", exc_info=True)
    #         raise


    def run(self,
            description: str,
            command: Union[str, list],
            chroot: bool = False,
            dryrun: bool = False,
            capture_output: bool = True,
            timeout: Optional[float] = None,
            check: bool = True,
            shell: bool = False,
            cwd: Optional[str] = None
            ) -> Tuple[int, str, str]:
        """
        Executes a shell command using the RichAppLogger's execution_step context manager
        for enhanced TUI feedback, logging, and centralized exception handling.
        """

        original_command_str = shlex.join(command) if isinstance(command, list) else command

        # Prepare the command list (handles shlex.split and arch-chroot prepending)
        prepared_command_list = self._prepare_command(command, chroot=chroot)

        if dryrun:
            self.logger.info(f"DRY RUN: Execution skipped for: '{description}'")
            self.logger.debug(f"DRY RUN COMMAND (Prepared): {shlex.join(prepared_command_list)}")
            return 0, "DRY_RUN_STDOUT", "DRY_RUN_STDERR"

        # --- CORE LOGIC: Reliance on logger.execution_step for TUI/Logging ---

        # 1. Start the context manager. It prints the RUNNING status to TUI and log file.
        with self.logger.execution_step(description):

            # Command passed to execute_command depends on the 'shell' flag
            cmd_to_pass = prepared_command_list if not shell else original_command_str

            # 2. Execute the low-level command. This call will either:
            #    a) Return successfully (exit_code 0).
            #    b) Raise a ShellCommandError (or subclass) if 'check=True' and exit_code != 0.
            #    c) Raise a general exception (e.g., TimeoutExpired, which execute_command converts).

            exit_code, stdout, stderr = self.execute_command(
                command=cmd_to_pass,
                capture_output=capture_output,
                timeout=timeout,
                check=check,
                shell=shell,
                cwd=cwd
            )

            # 3. Success Path (Only reached if execute_command completes without raising)
            #    When this block exits, logger.execution_step automatically:
            #    - Stops the TUI spinner (overwriting the [RUNNING] line).
            #    - Prints the final '✔ [COMPLETED]' message to the console.
            #    - Logs the final '[COMPLETED]' status to the file.

            # Log captured output at DEBUG level. This must be inside the 'with'
            # block to ensure it happens before the return, but after TUI status is resolved.
            self.logger.debug(f"Command '{description}' successfully completed. Output details:")
            if stdout:
                self.logger.debug(f"  Stdout:\n{stdout.strip()}")
            if stderr:
                self.logger.debug(f"  Stderr:\n{stderr.strip()}")

            return exit_code, stdout, stderr

        # NOTE: If an exception is raised inside the 'with' block, the logger.execution_step
        #       catches it, prints the '✘ [CRITICAL]' message, logs, and re-raises the exception.
        #       We do not need the outer try/except block.

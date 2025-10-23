# pure_arch/utils/executor.py
import subprocess
import time
import shlex
import os
import threading
from concurrent.futures import Future
from typing import Tuple, Optional, Union, List

from .. import core
from utils.logger import initialize_app_logger
from utils.exceptions import ShellCommandError, CommandNotFoundError, CommandTimeoutError, InvalidCommandError, PermissionDeniedError


# Set to global logger
logger = core.app_logger

if logger is None:
    core.app_logger = initialize_app_logger(app_name = __name__)
    logger = core.app_logger

class Executor:
    """
    A robust class for executing shell commands on Arch Linux, with enhanced
    logging, chroot support, dry-run capabilities, and a user-friendly run() method.
    Utilizes a custom global logger for consistent output.
    """

    def __init__(self, default_timeout: Optional[float] = 30.0, chroot_path: str = "/mnt"):
        """
        Initializes the Executor with an optional default timeout and chroot path.

        Args:
            default_timeout (Optional[float]): Default timeout in seconds for commands.
                                               If None, commands will run without a specific timeout
                                               unless specified otherwise in execute_command.
            chroot_path (str): The base path for chroot environments (e.g., '/mnt').
        """
        if default_timeout is not None and default_timeout <= 0:
            raise ValueError("Default timeout must be a positive number or None.")
        if not isinstance(chroot_path, str) or not chroot_path:
            raise ValueError("Chroot path must be a non-empty string.")

        self._default_timeout = default_timeout
        self._chroot_path = chroot_path
        logger.debug(f"Executor initialized with default_timeout: {self._default_timeout}, chroot_path: {self._chroot_path}")

    def _prepare_command(self, command: Union[str, list], chroot: bool) -> List[str]:
        """
        Prepares the command for execution by shlex.split if it's a string,
        and prepends arch-chroot if chroot is True.

        Args:
            command (Union[str, list]): The command to prepare. Can be a string or a list of arguments.
            chroot (bool): If True, prepend 'arch-chroot {self._chroot_path}'.

        Returns:
            list: The command as a list of arguments.

        Raises:
            InvalidCommandError: If the command is empty or not a string/list.
        """
        if not command:
            logger.error("Attempted to prepare an empty command.")
            raise InvalidCommandError(str(command), "Command cannot be empty.")

        if isinstance(command, str):
            try:
                # shlex.split handles shell-like parsing, including quoted arguments
                parsed_command = shlex.split(command)
            except ValueError as e:
                logger.error(f"Failed to parse command string '{command}': {e}")
                raise InvalidCommandError(command, f"Failed to parse command string: {e}")
        elif isinstance(command, list):
            if not all(isinstance(arg, str) for arg in command):
                raise InvalidCommandError(str(command), "All elements in command list must be strings.")
            parsed_command = command
        else:
            logger.error(f"Invalid command type: {type(command)}. Expected str or list.")
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

        Args:
            command (Union[str, list]): The command to execute. Can be a string or a list.
            capture_output (bool): If True, stdout and stderr are captured.
            timeout (Optional[float]): Timeout for the command.
            check (bool): If True, raises an exception on non-zero exit code.
            shell (bool): If True, the command is executed through the shell (use with caution).
            cwd (Optional[str]): The current working directory.

        Returns:
            Tuple[int, str, str]: A tuple containing (exit_code, stdout, stderr).

        Raises:
            ShellCommandError, CommandNotFoundError, CommandTimeoutError, InvalidCommandError,
            PermissionDeniedError
        """
        actual_timeout = timeout if timeout is not None else self._default_timeout
        cmd_string_for_log = shlex.join(command) if isinstance(command, list) else command
        logger.debug(f"Attempting low-level execution: '{cmd_string_for_log}' "
                     f"timeout={actual_timeout}s, capture_output={capture_output}, check={check}, shell={shell}")

        try:
            if shell:
                # If shell=True, command must be a string for subprocess.run
                if isinstance(command, list):
                    command_to_execute = shlex.join(command)
                else:
                    command_to_execute = command
            else:
                # If shell=False, command must be a list for subprocess.run
                command_to_execute = self._prepare_command(command, chroot=False) # chroot is handled by run()

            process = subprocess.run(
                command_to_execute,
                capture_output=capture_output,
                text=True,
                timeout=actual_timeout,
                check=False,  # We handle checking manually for custom exceptions
                shell=shell,
                cwd=cwd
            )

            stdout = process.stdout if capture_output and process.stdout else ""
            stderr = process.stderr if capture_output and process.stderr else ""
            exit_code = process.returncode

            if check and exit_code != 0:
                error_message = f"Command failed with exit code {exit_code}"
                logger.error(f"Command: '{cmd_string_for_log}', Exit Code: {exit_code}, Stderr: {stderr.strip()}")

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

            logger.debug(f"Low-level execution of '{cmd_string_for_log}' completed with exit code {exit_code}")
            return exit_code, stdout, stderr

        except FileNotFoundError:
            logger.error(f"Command '{cmd_string_for_log}' not found. Ensure it's in the system's PATH.")
            raise CommandNotFoundError(command=cmd_string_for_log, stdout="", stderr="Command not found. Check PATH.")
        except subprocess.TimeoutExpired as e:
            logger.warning(f"Command '{cmd_string_for_log}' timed out after {actual_timeout} seconds.")
            stdout = e.stdout.decode() if e.stdout else ""
            stderr = e.stderr.decode() if e.stderr else ""
            raise CommandTimeoutError(command=cmd_string_for_log, timeout=actual_timeout, stdout=stdout, stderr=stderr)
        except TypeError as e:
            logger.error(f"Type error during low-level command execution '{cmd_string_for_log}': {e}")
            raise InvalidCommandError(cmd_string_for_log, f"Type error in command arguments: {e}")
        except ValueError as e:
            logger.error(f"Value error during low-level command execution '{cmd_string_for_log}': {e}")
            raise InvalidCommandError(cmd_string_for_log, f"Value error in command arguments: {e}")
        except Exception as e:
            logger.critical(f"An unhandled exception occurred during low-level execution of '{cmd_string_for_log}': {e}", exc_info=True)
            raise ShellCommandError(cmd_string_for_log, -1, "", "", f"An unexpected error occurred: {e}")

    def run(self,
            description: str,
            command: Union[str, list],
            chroot: bool = False,
            verbose: bool = True,
            dryrun: bool = False,
            capture_output: bool = True,
            timeout: Optional[float] = None,
            check: bool = True,
            shell: bool = False,
            cwd: Optional[str] = None
            ) -> Tuple[int, str, str]:
        """
        Executes a shell command with enhanced features like description, chroot,
        verbosity control, and dry-run capability. This is the primary method to use.

        Args:
            description (str): A functional description of the command's purpose.
            command (Union[str, list]): The command to execute. Can be a string or a list.
            chroot (bool): If True, the command will be executed in a chroot environment
                           (prepended with 'arch-chroot /mnt').
            verbose (bool): If True, provides more detailed logging for this specific command.
            dryrun (bool): If True, logs all actions but does not execute the actual shell command.
                           Returns (0, "DRY_RUN_STDOUT", "DRY_RUN_STDERR") on dry run.
            capture_output (bool): If True, stdout and stderr are captured.
            timeout (Optional[float]): The maximum time in seconds to wait for the command to complete.
            check (bool): If True, raises a ShellCommandError if the command returns a non-zero exit code.
            shell (bool): If True, the command will be executed through the shell. Use with caution.
            cwd (Optional[str]): The current working directory to run the command in.

        Returns:
            Tuple[int, str, str]: A tuple containing (exit_code, stdout, stderr).
                                  On dry run, returns (0, "DRY_RUN_STDOUT", "DRY_RUN_STDERR").

        Raises:
            InvalidCommandError: If the command is malformed or empty.
            CommandNotFoundError: If the command itself cannot be found.
            CommandTimeoutError: If the command exceeds the specified timeout.
            PermissionDeniedError: If there's a permission issue executing the command.
            ShellCommandError: For any other non-zero exit code, or other unexpected errors.
        """
        original_command_str = shlex.join(command) if isinstance(command, list) else command
        prepared_command_list = self._prepare_command(command, chroot=chroot)
        full_command_for_log = shlex.join(prepared_command_list)

        logger.info(original_command_str)

        if dryrun:
            logger.execute(f"DRY RUN: Skipping actual execution for: '{description}'")
            time.sleep(0.05)
            logger.execute(f"DRY RUN: Completed simulation of '{description}'.", success=True)
            return 0, "DRY_RUN_STDOUT", "DRY_RUN_STDERR"

        try:
            # Use logger.execute for ongoing progress, if verbose
            if verbose:
                logger.execute(f"Running '{description}'...")
                time.sleep(1.05)

            exit_code, stdout, stderr = self.execute_command(
                command=prepared_command_list if not shell else original_command_str,
                capture_output=capture_output,
                timeout=timeout,
                check=check,
                shell=shell,
                cwd=cwd
            )

            if exit_code == 0:
                if verbose:
                    logger.execute(f"'{description}'", success=True)
                    logger.debug(f"  Stdout:\n{stdout.strip()}")
                    logger.debug(f"  Stderr:\n{stderr.strip()}")
                else:
                    logger.info(f"Successfully executed '{description}'. Exit Code: {exit_code}")
            else:
                if verbose:
                    logger.execute(f"'{description}'", success=False)
                    logger.error(f"Exit Code: {exit_code}")
                    logger.error(f"  Stdout:\n{stdout.strip()}")
                    logger.error(f"  Stderr:\n{stderr.strip()}")
                else:
                    logger.error(f"Command '{description}' failed. Exit Code: {exit_code}")

            return exit_code, stdout, stderr

        except ShellCommandError as e:
            logger.error(f"Error executing '{description}': {e}")
            raise # Re-raise the specific exception
        except Exception as e:
            logger.critical(f"An unexpected error occurred during run() for '{description}': {e}", exc_info=True)
            raise # Re-raise any unhandled exceptions

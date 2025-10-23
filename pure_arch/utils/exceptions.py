# pure_arch/utils/exceptions.py

class ShellCommandError(Exception):
    """Base exception for errors during shell command execution."""
    def __init__(self, command: str, exit_code: int, stdout: str, stderr: str, message: str = "Shell command failed"):
        self.command = command
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.message = message
        super().__init__(f"{self.message}: Command='{self.command}', Exit Code={self.exit_code}, "
                         f"Stdout='{self.stdout.strip()}', Stderr='{self.stderr.strip()}'")

class CommandNotFoundError(ShellCommandError):
    """Exception raised when the command itself is not found."""
    def __init__(self, command: str, stdout: str, stderr: str):
        super().__init__(command, 127, stdout, stderr, "Command not found") # 127 is common exit code for command not found

class CommandTimeoutError(ShellCommandError):
    """Exception raised when a shell command times out."""
    def __init__(self, command: str, timeout: float, stdout: str, stderr: str):
        self.timeout = timeout
        super().__init__(command, -1, stdout, stderr, f"Command timed out after {timeout} seconds")

class InvalidCommandError(ShellCommandError):
    """Exception raised for invalid or malformed commands."""
    def __init__(self, command: str, message: str = "Invalid command format"):
        super().__init__(command, -1, "", "", message)

class PermissionDeniedError(ShellCommandError):
    """Exception raised when a shell command encounters a permission denied error."""
    def __init__(self, command: str, stdout: str, stderr: str):
        super().__init__(command, 126, stdout, stderr, "Permission denied") # 126 is common exit code for permission denied

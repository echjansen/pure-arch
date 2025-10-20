# pure_arch/__init__.py

# Utility imports
from .utils.util_exceptions import ShellCommandError
from .utils.util_exceptions import CommandNotFoundError
from .utils.util_exceptions import CommandTimeoutError

# Import *
__all__ = [
    ShellCommandError,
    CommandNotFoundError,
    CommandTimeoutError,
]

# Versioning
__version__ = "0.0.0"

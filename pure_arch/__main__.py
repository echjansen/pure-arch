# pure_arch/__main__.py
from . import core
from pure_arch.cli import app
from pure_arch.utils.logger import initialize_app_logger
from pure_arch.utils.executor import Executor
from pure_arch.config.models import ArchInstallerConfig
from pure_arch.disk import prepare_disk

import os
import sys
from pathlib import Path


def logger():
    """
    Create global logging
    """
    core.app_logger = initialize_app_logger(app_name = __name__)


def main():
    """
    Main application
    """
    app()


def test_disk():
    """
    Test the preparation of the disk
    """

    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    # Get the parent directory (project root) and join the filename
    CONFIG_PATH = script_dir.parent / 'config.toml'

    # 1. Initialize Logger
    if core.app_logger is None:
        core.app_logger = initialize_app_logger(app_name = __name__)

    try:
        # 2. Load Config (Requires config.toml to be created)
        config_data = ArchInstallerConfig.load_config_from_file(Path(CONFIG_PATH))

        # 3. Initialize Executor (injecting the logger)
        exe = Executor(logger_instance=core.app_logger, chroot_path="/mnt")

        # 4. Run the disk preparation (Set dry_run=True for safety during testing)
        core.app_logger.info(config_data.display_summary())
        core.app_logger.warning("Running in DRY-RUN mode. Change 'dry_run' to False to execute.")

        prepare_disk(executor=exe, config=config_data, dry_run=False)

    except (ValueError, FileNotFoundError, Exception) as e:
        # Catch config loading errors or unexpected failures
        core.app_logger.critical(f"Setup terminated due to initialization error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    logger()
    test_disk()
    #main()

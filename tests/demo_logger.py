import time
import logging
from pure_arch.utils.logger import initialize_app_logger

# ==== Run with: python -m tests.demo_logger ====

# Set the console log level lower than default INFO if you want to see debug messages
LOGGER_LEVEL = logging.DEBUG

def main():
    # 1. Initialize the logger
    log = initialize_app_logger(
        app_name="ArchInstaller",
        log_file_name="demo.log",
        console_log_level=LOGGER_LEVEL
    )

    log.section("System Pre-Check Phase")
    log.info("Verifying user permissions...")
    log.debug("User ID: 1000, Group ID: 1000")

    # 2. Demonstrate EXECUTION Step (Success)
    try:
        with log.execution_step("Downloading Arch Linux kernel"):
            time.sleep(1.5) # Simulate work
            # The status spinner runs while this block executes

        log.info("Kernel download complete.")

    except Exception as e:
        # This catch is mostly a safety net for unexpected errors
        log.error(f"Failed to complete step: {e}")


    # 3. Demonstrate EXECUTION Step (Failure)
    log.section("Configuration Phase")
    try:
        with log.execution_step("Mounting root filesystem"):
            time.sleep(1)
            # Simulate a failure condition
            if True: # Always fail for demo
                raise FileNotFoundError("Target partition /dev/sda1 not found.")

    except Exception:
        # The execution_step context manager logs the failure and prints the rich traceback
        log.error("Setup terminated due to filesystem error.")
        # log.exception() is NOT needed here because execution_step already called print_exception

    log.critical("Application exit.")


if __name__ == "__main__":
    main()

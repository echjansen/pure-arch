# pure_arch/__main__.py
from . import core
from pure_arch.cli import app
from pure_arch.utils.logger import initialize_app_logger
from pure_arch.utils.executor import Executor

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

def test_executor():
    executor = Executor()
    executor.run("test 1", "ls -al", verbose=True)

if __name__ == "__main__":
    logger()
    #test_executor()

    main()

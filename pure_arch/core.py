# core.py
from typing import Optional
from pure_arch.utils.logger import RichAppLogger

# A global variable to hold the initialized logger wrapper
# It starts as None and will be set in main()
app_logger: Optional[RichAppLogger] = None

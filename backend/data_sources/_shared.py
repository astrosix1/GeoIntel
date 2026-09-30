"""
Shared setup used by every submodule in this package: env loading and the
module-level logger. Kept in one spot so all submodules stay consistent
(see data_sources/__init__.py for the package-level re-exports).
"""
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger('data_sources')

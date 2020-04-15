from .anysnake import Anysnake
from .parser import parse_requirements, parsed_to_anysnake

from pkg_resources import get_distribution, DistributionNotFound
try:
    __version__ = get_distribution(__name__).version
except DistributionNotFound:
    # package is not installed
    pass

__all__ = [Anysnake, parse_requirements, parsed_to_anysnake, __version__]

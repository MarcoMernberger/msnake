from .dockerator import Dockerator
from .parser import parse_requirements, parsed_to_dockerator

from pkg_resources import get_distribution, DistributionNotFound
try:
    __version__ = get_distribution(__name__).version
except DistributionNotFound:
    # package is not installed
    pass

__all__ = [Dockerator, parse_requirements, parsed_to_dockerator, __version__]

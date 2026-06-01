"""
Built-in verticals. Importing this package registers them all.
Add a new use case by dropping a module here that calls leadgen.register(...).
"""
from . import simply_tc      # noqa: F401  (registers "simply_tc")
from . import web_design     # noqa: F401  (registers "web_design")

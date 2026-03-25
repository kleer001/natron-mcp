"""
natronmcp — TCP JSON server that runs inside Natron's embedded Python.

Loaded via ~/.Natron/init.py at startup:

    import sys
    sys.path.insert(0, '/path/to/natron-mcp/src')
    import natronmcp
    natronmcp.start()
"""

from .server import start, stop

__all__ = ['start', 'stop']

"""
natron_keepalive.py — Passed to NatronRenderer via -s to start the Qt event loop.

Without this, NatronRenderer -t exits after init.py runs and the TCP server
daemon thread dies. Starting the event loop keeps the process alive and allows
QTimer to fire, which is required for the work queue to drain.

Usage (via launch.py --headless):
    NatronRenderer -t -s /path/to/natron_keepalive.py
"""

from PySide.QtCore import QCoreApplication

app = QCoreApplication.instance()
if app is not None:
    app.exec_()
else:
    import sys
    print('[natron-mcp] ERROR: no QCoreApplication instance — keepalive failed', file=sys.stderr)

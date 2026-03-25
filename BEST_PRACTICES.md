# natron-mcp Best Practices

Hard-won API facts discovered while building natron-mcp. Read this before
touching NatronEngine code or debugging connection issues.

---

## App Access

**Problem:** `app` and `natron.getInstance()` don't exist as globals.
**Fix:** Probe `__main__` in order: `app1`, `app2`, `app`.

```python
import __main__
for name in ('app1', 'app2', 'app'):
    a = getattr(__main__, name, None)
    if a is not None:
        return a
```

A fresh unnamed project returns `None` from `get_scene_info` — use
`execute_python` to inspect `app1` directly if you suspect a false negative.

---

## Node Operations

**Problem:** `app.deleteNode(node)` raises AttributeError — it doesn't exist.
**Fix:** Call `node.destroy()` directly on the node object.

**Problem:** `connectInput` is on the Effect (node), not the App.
**Fix:** `dst_node.connectInput(input_index, src_node)` — note dst is the receiver.

**Problem:** `getChildren()` and `getNode(name)` are inherited from Group, not
directly on App. They work, but don't look for them in the App API docs.

---

## Parameter Values

**Problem:** Colour parameters have dimensions (R=0, G=1, B=2, A=3).
`param.setValue(value)` without a dimension index sets dimension 0 only.
**Fix:** Pass explicit dimension: `param.setValue(value, dimension)`.

**Note:** `param.getValue()` with no args returns dimension 0. Use
`param.getValue(dimension)` to read a specific channel.

---

## Main-Thread Dispatch (QTimer)

**Problem:** `createNode` (and most NatronEngine calls) crash if called from a
background socket thread. Natron is Qt4 and not thread-safe.

**Fix:** The `start()` function must be called from the main thread (via
`~/.Natron/init.py`). It installs a `QTimer` that drains a work queue every
10ms. All NatronEngine commands are posted to the queue and block on a
`threading.Event` until the main thread executes them.

**Critical:** Create `QTimer()` in `start()` (called on main thread). Do NOT
use `QTimer.singleShot(ms, callable)` — it is unreliable in this environment.

```python
from PySide.QtCore import QTimer
_drain_timer = QTimer()              # must be created on main thread
_drain_timer.timeout.connect(fn)
_drain_timer.start(10)
```

Keep a reference to the timer object (`_drain_timer = ...`). If it goes out of
scope, the GC collects it and the timer stops silently.

---

## Qt / PySide Version

Natron 2.5.0 links `libQtCore.so.4` — this is **Qt4**, not Qt5. PySide
version is 1.2.4 (Qt4 bindings). Do not attempt to import `PySide2` or `PyQt5`.

---

## Node Input Wiring (specific nodes)

Inputs verified empirically (not always obvious from docs):

| Node       | Input 0     | Input 1          | Input 2 |
|------------|-------------|------------------|---------|
| KeyMix     | B (mask=0)  | A (mask=1)       | Mask    |
| MergeScreen| B (background) | A (overlay)   | —       |
| Merge      | B (base)    | A (overlay)      | Mask    |

---

## Auto-arrange Nodes

The keyboard shortcut to auto-arrange selected nodes is **L**.
Caveat: pressing L with no nodes selected (or viewer focused) controls timeline
playback instead. Select nodes first.

---

## get_scene_info on Fresh Projects

A fresh untitled project returns `"No project open"` or empty strings from
`getProjectParam`. Workaround: call `execute_python` with code that reads
`app1` attributes directly.

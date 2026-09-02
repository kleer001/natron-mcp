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

## Rendering

`app.render(effect, firstFrame, lastFrame)` is **non-blocking in GUI mode** —
it returns immediately and Natron renders in the background. Do not expect a
blocking call in normal (GUI) usage.

**Pattern:** call `render()` to start, then call `monitor_render(output_path)`
to poll the filesystem until the output file appears. `monitor_render` runs
entirely on the bridge side (no Natron TCP connection) and uses `time.sleep`
polling — no timeout concerns on the Natron side.

**Background mode (NatronRenderer):** `app.render()` is blocking. The current
MCP server is not optimised for background mode (see todo.md headless section).

---

## load_project (headless SIGSEGV)

`app.loadProject(filename)` **crashes NatronRenderer with SIGSEGV** when called
from a keepalive session (inside `exec_()`). The crash occurs in Natron's Python
attribute binder: `declarePythonFields(): attribute app.NodeName is not defined`.

**Cause:** When NatronRenderer loads a project inside `exec_()`, it tries to bind
node script names as Python attributes on `app` (not `app1`), but `app` is not in
`__main__` in that context.

**Workaround:** Call `load_project` in the startup script *before* `exec_()`.
Live-tested: `app1.loadProject(path)` returns a valid App object when called
before the event loop starts. After that, `createNode` also works before `exec_()`.

```python
import __main__
app = __main__.app1
app.loadProject('/path/to/project.ntp')             # safe before exec_()
node = app.createNode('net.sf.openfx.GradePlugin')  # safe before exec_()
from PySide.QtCore import QCoreApplication
QCoreApplication.instance().exec_()                  # keep alive
```

**`createNode` returns None** from QTimer callbacks while `exec_()` is running
(NatronRenderer re-entrancy). All node-creation tools (`create_node`,
`create_backdrop`, `setup_write_node`) are broken in headless MCP mode for
this reason.

---

## Headless vs GUI Tool Tiers

**Live-tested on NatronRenderer 2.5 (`-t` mode).**

`NatronRenderer -t` exposes `app1` (type `NatronEngine.App`) but not `GuiApp`.
`create_node` (and `create_backdrop`, `setup_write_node`) return `None` inside
the QTimer work queue even with a project open — NatronRenderer re-entrancy
restriction. They must be called in the startup `-s` script before `exec_()`.

| Tool | Headless? | Reason |
|------|-----------|--------|
| `ping` | ✅ safe | no NatronEngine calls |
| `get_scene_info` | ✅ safe | project params only |
| `list_nodes` | ✅ safe | `app.getChildren()` |
| `get_node_info` | ✅ safe | param/input reads |
| `get_parameter` | ✅ safe | `param.getValue()` |
| `set_parameter` | ✅ safe | `param.setValue()` |
| `set_expression` | ✅ safe | `param.setExpression()` — live tested ✓ |
| `get_expression` | ✅ safe | `param.getExpression()` — live tested ✓ |
| `clear_expression` | ✅ safe | `setExpression('', False, dim)` — live tested ✓ |
| `connect_nodes` | ✅ safe | `dst.connectInput()` |
| `delete_node` | ✅ safe | `node.destroy()` |
| `execute_python` | ✅ safe | exec in `__main__` |
| `save_project` | ✅ safe | `app.saveProject()` |
| `get_frame` | ✅ safe | `app.timelineGetTime()` |
| `set_project_settings` | ✅ safe | `getProjectParam()` |
| `set_node_position` | ✅ safe | `node.setPosition()` |
| `set_node_label` | ✅ safe | `node.setLabel()` |
| `set_node_color` | ✅ safe | `node.setColor()` |
| `render` | ✅ safe | `app.render()` (blocking headless) |
| `monitor_render` | ✅ safe | bridge-side filesystem poll |
| `list_plugin_ids` | ✅ safe | `NatronEngine.natron.getPluginIDs()` |
| `modify_node` | ✅ safe | `param.setValue()` loop |
| `find_nodes_by_type` | ✅ safe | `app.getChildren()` filter |
| `batch_set_knob` | ✅ safe | `param.setValue()` loop |
| `search_docs` | ✅ safe | bridge-side BM25, no Natron |
| `get_doc` | ✅ safe | bridge-side file read |
| `create_node` | ❌ headless broken | `app.createNode()` returns `None` from QTimer (re-entrancy) |
| `create_backdrop` | ❌ headless broken | same — `createNode('BackDrop')` returns `None` |
| `setup_write_node` | ⚠️ assumed broken | `app.createWriter()` not tested headless; likely same re-entrancy issue |
| `set_frame` | ❌ GUI only | `GuiApp.getViewer()` absent in headless — live tested ✓ |
| `load_project` | ❌ MCP broken | SIGSEGV when called via QTimer; only safe in startup script before `exec_()` |

**Headless launch** — the bash wrapper (`NatronRenderer`) exits prematurely
when stdin is a closed pipe. Use the actual ELF binary (`bin/NatronRenderer`)
and pipe from an infinite stdin source:

```bash
tail -f /dev/null | bin/NatronRenderer -t -s natron_keepalive.py
```

`scripts/launch.py --headless` handles this automatically.

## set_frame (GUI only)

`set_frame` uses `GuiApp.getViewer(name).seek(frame)`. This requires:
1. GUI mode (NatronRenderer does not have `getViewer`)
2. At least one Viewer node in the project

If `set_frame` raises "No Viewer node in project", add a Viewer node first.
If it raises "set_frame requires GUI mode", the server is running headless.

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

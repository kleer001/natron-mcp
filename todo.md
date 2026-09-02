# natron-mcp todo

## Bulk-up tooling

Tools added in this pass (now at 27: ping, get_scene_info, list_nodes, create_node,
get_node_info, get_parameter, set_parameter, connect_nodes, delete_node, execute_python,
save_project, load_project, get_frame, set_frame, set_project_settings, set_node_position,
set_node_label, set_node_color, render, create_backdrop, list_plugin_ids,
modify_node, find_nodes_by_type, batch_set_knob, setup_write_node,
search_docs, get_doc):

- ✅ `save_project` — `app.saveProject(filename)`
- ✅ `load_project` — `app.loadProject(filename)`
- ✅ `set_frame` — `GuiApp.getViewer(name).seek(frame)` (GUI mode only, needs Viewer node)
- ✅ `get_frame` — `app.timelineGetTime()`
- ✅ `set_project_settings` — fps via `frameRate`, frame range via `frameRange` dim 0/1
- ✅ `set_node_position` — `node.setPosition(x, y)`
- ✅ `set_node_label` — `node.setLabel(name)`
- ✅ `render` — `app.render(effect, first, last, step)`; 3600s timeout
- ✅ `list_plugin_ids` — `NatronEngine.natron.getPluginIDs([filter])`
- ✅ `set_node_color` — `node.setColor(r, g, b)`
- ✅ `create_backdrop` — `app.createNode('fr.inria.built-in.BackDrop')`
- ✅ `modify_node` — set multiple params on one node in one call
- ✅ `find_nodes_by_type` — filter `app.getChildren()` by plugin_id
- ✅ `batch_set_knob` — set same param on multiple nodes
- ✅ `setup_write_node` — `app.createWriter(file_path)` + optional connect

Still unimplemented (no Natron API exists or needs more investigation):

- ✅ `set_expression` — `param.setExpression(expr, has_return_var, dimension)` implemented and live-tested
- ✅ `get_expression` — `param.getExpression(dimension)` → (expr, has_return_var) — implemented and live-tested
- ✅ `clear_expression` — `param.setExpression('', False, dimension)` — implemented and live-tested
- `get_viewer_info` — no `getViewer()` in headless; in GUI mode `app.getViewer(name)` exists but not yet exposed as a tool
- `find_error_nodes` — **confirmed no API**: no error/warn/status attrs on nodes; skip
- `duplicate_node` — **confirmed no API**: no copy/paste/select/duplicate methods on App or Effect; skip
- `group_nodes` — **confirmed**: `app.createNode('fr.inria.built-in.Group')` creates a Group with default children (`Output1`, `Input1`). Works before `exec_()` in headless; broken during exec_() (re-entrancy). In GUI mode this works normally via `create_node`.

## Headless mode investigation

`NatronRenderer` is Natron's CLI renderer. With the `-t` (background/terminal)
flag it loads `~/.Natron/init.py`, which means the TCP server starts. Possible:
- `QCoreApplication` runs the event loop → `QTimer` should work
- App vs GuiApp: `NatronRenderer` exposes `app` (not `GuiApp`), so GUI-only calls
  (viewer, color picker, etc.) will fail

Investigation tasks (all completed via live NatronRenderer 2.5 testing):
1. ✅ Launch `NatronRenderer -t` and verify TCP server starts — confirmed working (use `bin/NatronRenderer` ELF directly, not bash wrapper; pipe stdin with `tail -f /dev/null`)
2. ✅ Identify which tools work headless — see BEST_PRACTICES.md tier table
3. ✅ Identify which tools require `GuiApp` — `set_frame` (getViewer), `load_project` (SIGSEGV from QTimer); also `create_node`/`create_backdrop`/`setup_write_node` broken by re-entrancy
4. ✅ Document two tiers — updated BEST_PRACTICES.md with live-tested results
5. ✅ Add headless launch support to `scripts/launch.py` (`--headless` flag) — uses `bin/NatronRenderer` + `tail -f /dev/null` stdin pipe

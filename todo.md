# natron-mcp todo

## Bulk-up tooling

Additional MCP tools to implement (currently have 10: ping, get_scene_info,
list_nodes, create_node, get_node_info, get_parameter, set_parameter,
connect_nodes, delete_node, execute_python):

- `save_project` — save the current project to disk
- `load_project` — open a .ntp file
- `set_frame` — set current frame
- `get_frame` — get current frame
- `set_project_settings` — set fps, frame range, etc.
- `set_node_position` — set node position in the graph (x, y)
- `set_node_label` — rename a node's display label
- `render` — render current frame or frame range to disk
- `get_viewer_info` — get active viewer node / display node
- `set_expression` — set a parameter expression (Python or Natron expression)
- `find_error_nodes` — list nodes that have errors
- `duplicate_node` — copy a node
- `list_plugin_ids` — enumerate available plugin IDs (NatronEngine.natron.getPluginIDs())
- `set_node_color` — set node tile color (NatronEngine Color)
- `create_backdrop` — create a BackDrop node
- `group_nodes` — group selected nodes

## Headless mode investigation

`NatronRenderer` is Natron's CLI renderer. With the `-t` (background/terminal)
flag it loads `~/.Natron/init.py`, which means the TCP server starts. Possible:
- `QCoreApplication` runs the event loop → `QTimer` should work
- App vs GuiApp: `NatronRenderer` exposes `app` (not `GuiApp`), so GUI-only calls
  (viewer, color picker, etc.) will fail

Investigation tasks:
1. Launch `NatronRenderer -t` and verify TCP server starts
2. Identify which of the 10 existing tools work headless
3. Identify which tools require `GuiApp` (and fail headless)
4. Document two tiers: "headless-safe" vs "GUI-only" — update BEST_PRACTICES.md
5. Add headless launch support to `scripts/launch.py` (`--headless` flag)

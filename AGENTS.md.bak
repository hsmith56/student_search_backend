# lean-ctx — CLI-first Token Optimization for Pi

This project uses the **pi-lean-ctx** extension. It routes Pi’s built-in tools through **lean-ctx CLI**
for strong token savings — **no MCP required**.

## What to do (as Pi agent)

- Use Pi tools normally:
  - `read` (never `cat/head/tail` via bash)
  - `grep` / `find` / `ls`
  - `bash` for commands with side effects (build/test/git/etc.)
- The extension auto-routes these through `lean-ctx` and appends a savings footer where possible.

## Advanced lean-ctx commands (still CLI-only)

Prefer the `lean_ctx` tool (installed by the extension) to run `lean-ctx` directly:

- `lean-ctx overview`
- `lean-ctx session …`
- `lean-ctx knowledge …`
- `lean-ctx gain` / `lean-ctx stats`
- `lean-ctx index …`

If `lean_ctx` is not available, use Pi’s `bash` tool with `raw=true` to run `lean-ctx …` directly
(avoid nesting `lean-ctx` inside its own compression wrapper).

## Optional MCP (disabled by default)

Some users enable MCP for additional tools. If MCP is enabled, it will show up in `/lean-ctx`,
but the default workflow is CLI-first.

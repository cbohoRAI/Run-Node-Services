# High-Level Concept

Replace the tab bar in `SimpleLogViewer` with a passive display that always holds all log entries internally, but only renders:

- **All logs (default)**, OR
- **Logs for the currently “selected” project** (selection driven externally by `RunningPanel`)

The `RunningPanel` becomes the single source of truth for which project (if any) is selected. User interaction shifts from “change tab” to “click a project name.” Keyboard shortcuts can still exist (e.g., cycle selection, clear selection for “All Logs”).

---

## Goals

- Eliminate duplicated navigation (panel + tabs).
- Provide more intuitive UX: select the project where you manage processes to view its logs.
- Keep performance acceptable for continuous log streaming.
- Minimize invasive changes—extend existing callback/event patterns.

---

## Affected Components

- **RunningPanel**: Add selection state, click handling, and event emission.
- **SimpleLogViewer**: Remove tab bar, expose `set_active_project(project: Optional[str])`.
- **MonitoringScreen**: Wire selection events to log viewer; remove key bindings for tabs.
- **Key bindings**: Repurpose or prune “tab_x” actions; maybe add “a” for All Logs.

---

## Data & State Flow

- **Log collection unchanged**: `LogCollector` invokes `MonitoringScreen._on_log_line(project, line)`.
- **MonitoringScreen**: Formats and forwards to `SimpleLogViewer.add_log(project, text)`.
- **SimpleLogViewer**: Stores every log entry in an in-memory list: `List[Tuple[str, Text]]`.
- **RunningPanel**: Emits a selection event (custom message or callback) when a user clicks a project row.
- **MonitoringScreen**: Receives that event and calls `log_viewer.set_active_project(name_or_None)`.
- **SimpleLogViewer**: Re-renders only matching entries (or all if None).

---

## UX Behavior Specs

- **Initial state**: No project selected → All logs streaming.
- **Click a project row**: Becomes selected → Only that project’s logs display (historical + streaming).
- **Click same selected project again (toggle behavior)**: Clears selection → All logs.
- **Keyboard**:
  - Up/Down (if already implemented for navigation) moves selection and updates logs.
  - New binding (e.g., “a” or ESC) → clear selection (All Logs).
  - Remove old numeric tab bindings & “next_tab”.
- **Visual cues**:
  - Selected project row highlighted (ensure style persists).
  - Log viewer shows a small header/status line (optional): `[Viewing: api-service] Press A to show all.`
  - When filtered, maybe prepend a subtle dim line: `--- Filter: api-service ---`.

---

## Proposed API / Contract Changes

### SimpleLogViewer (new/changed)

- **Remove**: tab rendering methods (`_build_tabs`, `_update_tab_styles`, `next_tab`, `select_tab_index`, `tab_count`)
- **Add**:
  - `set_active_project(project: Optional[str]) -> None`
  - `get_active_project() -> Optional[str]`
  - `clear()` (maybe keep; internal reuse)
- **Internal**:
  - `_active_project: Optional[str]`
  - `_refresh_display()` (reuse; simplified: no tab styles)

### RunningPanel (new)

- **Selection management**:
  - `set_selected(project: Optional[str]) -> None`
  - `get_selected() -> Optional[str]`
  - `toggle_selected(project: str) -> None`
- **Event/message emission** (choose one pattern):
  - Textual Message subclass: `ProjectSelected(project: Optional[str])`
  - Callback registration interface.
  - Simpler: `post_message(ProjectSelected(self, project))`
- **User interaction**:
  - On click row → toggle or set
  - On key (if focus in panel) → arrow navigation updates selection + emits event

### MonitoringScreen (adjustments)

- **Remove actions**: `action_next_tab`, `action_tab_1...action_tab_9`
- **Add**:
  - `action_show_all_logs() -> calls log_viewer.set_active_project(None)`
  - Handle project selection message: `on_project_selected(msg) -> log_viewer.set_active_project(msg.project)`

### Key Bindings (revision)

- **Remove**: (“tab”, “next_tab”), (“1”..“9”, “tab_n”)
- **Add**: (“a”, “show_all_logs”, “All Logs”)
- **Optionally**: (“enter” or “space”) could toggle selection while panel focused (if not already default)

---

## Event Mechanism Choice

**Recommendation**: Use a Textual Message for future extensibility.

**Example (interface only, not implementation):**
```python
class ProjectSelected(Message):
    def __init__(self, sender: RunningPanel, project: Optional[str]) -> None:
        ...
```
**Pros**: Decouples `RunningPanel` and `MonitoringScreen`; allows future listeners.

---

## Edge Cases & Handling

- **Project removed/crashes**: If currently selected, keep showing historical logs (OK) or auto revert to All Logs (recommend keep selection until user changes).
- **Project name changes (unlikely)**: Treat as a new project; old logs remain under old name.
- **High log volume**: Filtering requires full re-render on selection change—optimize by:
  - Avoid re-render for each incoming line when filtered? (Still needed; but acceptable unless tens of thousands of lines)
  - Optional: a max buffer size (configurable) with ring behavior.
- **Memory growth**: Implement optional retention cap (e.g., `max_lines=5000`).
- **Race condition**: Selection changes while lines stream → fine; each append checks active filter.

---

## Performance Considerations

- **Filtering now happens only on**:
  - Selection change (full re-render)
  - Append (write only if matches filter or filter unset)
- **Complexity per append**: O(1) when writing (no filtering pass).
- **Full re-render**: O(N) lines; acceptable if infrequent. If N grows large, consider:
  - Track a pre-filtered list per project (`dict[str, list[int]]`) referencing indices.
  - Or incremental virtualization (future enhancement).

---

## Implementation Phases

1. Strip tab UI from `SimpleLogViewer`.
2. Add selection state/data API.
3. Implement selection event in `RunningPanel`.
4. Wire event in `MonitoringScreen`.
5. Remove old bindings; add new binding(s).



---

## Risks & Mitigations

- **Missing visual indicator for filter** → Add header line.
- **User unaware how to get back to all logs** → Provide binding + status hint.
- **Large memory usage over long sessions** → Add configurable `max_entries` (evict oldest).

---

## Possible Enhancements (Later)

- Search / filter prompt (regex, severity)
- “Pin” multiple projects (multi-select) → display merged filtered subset
- Color-coded borders when filtered
- Export logs (current filter vs entire buffer)
- Lazy load / pagination for very large buffers

---

## Migration / Backward Compatibility

- No external API references to tab actions? (Search before removal.)
- Remove obsolete actions to avoid dangling bindings.
- If external scripts rely on actions (unlikely), keep stubs that no-op/log deprecation.

---

## Summary of Planned File Changes (No Code Yet)

- `simple_log_viewer.py`: remove tab UI; add selection API.
- `running_panel.py`: add selection tracking + message.
- `monitoring.py`: remove tab-related actions; add handler for selection; simplify key bindings.
- `README.md` (or usage docs): update navigation instructions.
- `tests`: add new test file or extend existing ones.

---


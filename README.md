# Node.js Project Runner - File Structure

This refactored version divides the original monolithic `services.py` file into a well-organized, modular structure that's easier to work with and maintain.

## File Structure

```
project-runner/
├── main.py                     # Main entry point
├── models/
│   ├── __init__.py
│   └── data.py                 # Data models (Project, RunningProject)
├── utils/
│   ├── __init__.py
│   ├── port.py                 # Port detection and process management
│   ├── loader.py               # Project configuration loader
│   └── logging.py              # Log management and buffering
├── ui/
│   ├── __init__.py
│   └── widgets.py              # Custom UI widgets
├── app/
│   ├── __init__.py
│   ├── runner.py               # Main application class
│   ├── actions.py              # Action methods and UI management
│   └── process_manager.py      # Process management methods
└── projects.txt                # Project configuration file (auto-generated)
```

## File Descriptions

### Core Files

- **`main.py`**: Entry point that handles command-line arguments and starts the application
- **`models/data.py`**: Contains data structures (`Project`, `RunningProject`) used throughout the app

### Utility Classes

- **`utils/port.py`**: Port detection utilities for finding ports in .env files and package.json, plus process management by port
- **`utils/loader.py`**: Loads and parses the projects configuration file
- **`utils/logging.py`**: Log management classes including buffering and multi-widget output

### UI Components

- **`ui/widgets.py`**: Custom Textual widgets like `StatusWidget` and `CollapsibleRunningPanel`

### Application Core

- **`app/runner.py`**: Main application class that inherits from all mixins and contains the core UI structure
- **`app/actions.py`**: All user action methods (keyboard shortcuts, UI interactions) and UI management utilities
- **`app/process_manager.py`**: Process lifecycle management (starting, monitoring, cleanup)

## Key Benefits of This Structure

1. **Separation of Concerns**: Each file has a clear, focused responsibility
2. **Easier Testing**: Individual components can be tested in isolation
3. **Better Maintainability**: Changes to one aspect (e.g., port detection) don't require touching other files
4. **Improved Readability**: Each file is smaller and more focused
5. **Modular Design**: Components can be reused or replaced independently

## Usage

Install dependencies:
```bash
pip install textual
```

Run the application:
```bash
python main.py
```

Or with a custom configuration file:
```bash
python main.py --file my_projects.txt
```

## Dependencies Between Files

- `main.py` → `app/runner.py`
- `app/runner.py` → `models/data.py`, `utils/*`, `ui/widgets.py`, `app/actions.py`, `app/process_manager.py`
- `app/actions.py` → `utils/port.py`
- `app/process_manager.py` → `models/data.py`, `utils/logging.py`, `utils/port.py`
- `ui/widgets.py` → `models/data.py`
- `utils/loader.py` → `models/data.py`

This structure makes the codebase much more maintainable while preserving all the original functionality.
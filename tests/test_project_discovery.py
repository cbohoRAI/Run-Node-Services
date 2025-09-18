from pathlib import Path
import json
from src.core.project_discovery import discover_projects

def create_package(path: Path, name: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "package.json").write_text('{"name": "%s"}' % name)


def test_discover_projects_finds_valid_projects(tmp_path: Path) -> None:
    create_package(tmp_path / "proj1", "proj-one")
    create_package(tmp_path / "proj2", "proj-two")
    projects = discover_projects(tmp_path)
    names = {p.name for p in projects}
    assert {"proj-one", "proj-two"} == names


def test_discover_projects_ignores_node_modules(tmp_path: Path) -> None:
    nm = tmp_path / "x" / "node_modules" / "pkg"
    create_package(nm, "should-ignore")
    projects = discover_projects(tmp_path)
    assert all("ignore" not in p.name for p in projects)


def test_config_file_overrides_scan(tmp_path: Path) -> None:
    # Create a real project that WOULD be discovered
    create_package(tmp_path / "scan_proj", "scan-proj")
    # Provide config that lists only a different project path
    cfg = [
        {
            "name": "listed",
            "path": str((tmp_path / "custom").mkdir() or (tmp_path / "custom")),
            "port": 5555,
            "start_command": ["npm", "start"],
        }
    ]
    (tmp_path / "projects.json").write_text(json.dumps(cfg))
    projects = discover_projects(tmp_path)
    names = {p.name for p in projects}
    assert names == {"listed"}
    assert projects[0].port == 5555


def test_short_name_parsed(tmp_path: Path) -> None:
    cfg = [
        {
            "name": "very-long-service-name",
            "short_name": "svcA",
            "path": str((tmp_path / "svcA").mkdir() or (tmp_path / "svcA")),
        }
    ]
    (tmp_path / "projects.json").write_text(json.dumps(cfg))
    projects = discover_projects(tmp_path)
    assert len(projects) == 1
    p = projects[0]
    assert p.name == "very-long-service-name"
    assert getattr(p, "short_name", None) == "svcA"

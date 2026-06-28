"""Package manager: resolve, download, and install briq packages."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


KNOWN_REGISTRY = {
    "briq-utils": {
        "description": "SQL utility macros and helpers for briq",
        "version": "0.1.0",
        "git": "https://github.com/briq-dev/briq-utils.git",
    },
    "briq-expectations": {
        "description": "Data quality test templates for briq",
        "version": "0.1.0",
        "git": "https://github.com/briq-dev/briq-expectations.git",
    },
}


def _packages_dir(project_path: Path) -> Path:
    return project_path / "briq_packages"


def _lock_path(project_path: Path) -> Path:
    return project_path / "briq.lock"


def _load_lock(project_path: Path) -> dict:
    lock = _lock_path(project_path)
    if lock.exists():
        return json.loads(lock.read_text(encoding="utf-8"))
    return {"packages": {}}


def _save_lock(project_path: Path, data: dict):
    _lock_path(project_path).write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )


def add_package(project_path: Path, name: str, source: Optional[str] = None, version: Optional[str] = None):
    lock = _load_lock(project_path)
    entry: dict = {"source": source or name}
    if version:
        entry["version"] = version
    lock["packages"][name] = entry
    _save_lock(project_path, lock)


def remove_package(project_path: Path, name: str):
    lock = _load_lock(project_path)
    lock["packages"].pop(name, None)
    _save_lock(project_path, lock)
    pkg_dir = _packages_dir(project_path) / name
    if pkg_dir.exists():
        shutil.rmtree(pkg_dir)


def list_packages(project_path: Path) -> list[dict]:
    lock = _load_lock(project_path)
    result = []
    for name, info in lock.get("packages", {}).items():
        pkg_dir = _packages_dir(project_path) / name
        exists = pkg_dir.exists()
        entry = {
            "name": name,
            "source": info.get("source", name),
            "installed": exists,
        }
        if "version" in info:
            entry["version"] = info["version"]
        result.append(entry)
    return result


def install_packages(project_path: Path):
    """Install all packages listed in briq.lock into briq_packages/."""
    lock = _load_lock(project_path)
    pkgs_dir = _packages_dir(project_path)

    for name, info in lock.get("packages", {}).items():
        source = info.get("source", name)
        pkg_dir = pkgs_dir / name
        if pkg_dir.exists():
            shutil.rmtree(pkg_dir)
        pkg_dir.mkdir(parents=True, exist_ok=True)

        if source.startswith(".") or "/" in source or "\\" in source:
            src_path = Path(source).resolve()
            if src_path.is_dir():
                _install_from_dir(src_path, pkg_dir)
            else:
                raise ValueError(f"Package source not found: {source}")
        elif source.endswith(".git") or source.startswith("git@"):
            _install_from_git(source, pkg_dir)
        elif source in KNOWN_REGISTRY:
            registry_info = KNOWN_REGISTRY[source]
            _install_from_registry(name, pkg_dir, registry_info)
        else:
            _install_from_registry(name, pkg_dir)


def search_packages(query: str = "") -> list[dict]:
    results = []
    for name, info in KNOWN_REGISTRY.items():
        if query and query.lower() not in name.lower() and query.lower() not in info.get("description", "").lower():
            continue
        results.append({
            "name": name,
            "description": info["description"],
            "version": info["version"],
        })
    return results


def package_info(name: str) -> Optional[dict]:
    if name in KNOWN_REGISTRY:
        info = KNOWN_REGISTRY[name]
        return {
            "name": name,
            "description": info["description"],
            "version": info["version"],
            "source": info.get("git", f"https://github.com/briq-dev/{name}"),
        }
    return None


def create_package(project_path: Path, name: str):
    pkg_dir = _packages_dir(project_path) / name / "models"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    pkg_file = pkg_dir.parent / "package.yml"
    if not pkg_file.exists():
        pkg_file.write_text(
            f"name: {name}\n"
            f"version: 0.1.0\n"
            f"description: ''\n"
            f"author: ''\n"
            f"license: Apache-2.0\n",
            encoding="utf-8",
        )
    example = pkg_dir / "example.sql"
    if not example.exists():
        example.write_text(
            "-- description: Example model\n"
            "select 1 as id\n",
            encoding="utf-8",
        )
    return pkg_dir.parent


def _install_from_dir(src: Path, dest: Path):
    for item in src.iterdir():
        if item.name.startswith("."):
            continue
        dest_item = dest / item.name
        if item.is_dir():
            shutil.copytree(item, dest_item, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest_item)


def _install_from_git(url: str, dest: Path):
    try:
        subprocess.run(
            ["git", "clone", url, str(dest)],
            capture_output=True, text=True, check=True, timeout=60,
        )
    except FileNotFoundError:
        raise ValueError("Git is not installed. Install git or use a local path source.")
    except subprocess.CalledProcessError as e:
        raise ValueError(f"Failed to clone {url}: {e.stderr.strip()}")


def _install_from_registry(name: str, dest: Path, registry_info: Optional[dict] = None):
    if registry_info and "git" in registry_info:
        _install_from_git(registry_info["git"], dest)
        return
    readme = dest / "README.md"
    if not readme.exists():
        readme.write_text(f"# {name}\n\nSee https://github.com/briq-dev/{name}\n", encoding="utf-8")

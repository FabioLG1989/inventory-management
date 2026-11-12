"""Detect the technology stack of a repository by inspecting manifest and lockfile markers.

Emits a JSON object to stdout and writes stack.json to --out-dir. Reads
framework-config.json when present and prefers its by_service language map as
the authoritative source (produced by the Phase 1 analyzer).

Supports: Python, JavaScript/TypeScript, Go, Rust, Java, Ruby, PHP, .NET, C/C++,
and IaC (Dockerfile, Terraform, Kubernetes manifests).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


MANIFEST_LANGUAGE_MAP: dict[str, str] = {
    "pyproject.toml": "python",
    "setup.py": "python",
    "setup.cfg": "python",
    "requirements.txt": "python",
    "Pipfile": "python",
    "Pipfile.lock": "python",
    "poetry.lock": "python",
    "uv.lock": "python",
    "package.json": "javascript",
    "package-lock.json": "javascript",
    "pnpm-lock.yaml": "javascript",
    "yarn.lock": "javascript",
    "go.mod": "go",
    "go.sum": "go",
    "Cargo.toml": "rust",
    "Cargo.lock": "rust",
    "pom.xml": "java",
    "build.gradle": "java",
    "build.gradle.kts": "java",
    "Gemfile": "ruby",
    "Gemfile.lock": "ruby",
    "composer.json": "php",
    "composer.lock": "php",
}

GLOB_LANGUAGE_MAP: list[tuple[str, str]] = [
    ("*.csproj", "dotnet"),
    ("packages.lock.json", "dotnet"),
    ("CMakeLists.txt", "c_cpp"),
    ("*.h", "c_cpp"),
    ("*.c", "c_cpp"),
    ("*.cpp", "c_cpp"),
    ("Dockerfile", "iac"),
    ("Dockerfile.*", "iac"),
    ("*.tf", "iac"),
]

IAC_EXTENSIONS = {".tf", ".yaml", ".yml"}
IAC_DIRS = {"k8s", "kubernetes", "infra", "terraform", "helm", "charts"}


def _detect_from_framework_config(repo_path: Path, config_dir: str) -> list[str] | None:
    config_path = repo_path / config_dir / "framework-config.json"
    if not config_path.exists():
        return None
    try:
        config = json.loads(config_path.read_text())
        by_service: dict = config.get("by_service", {})
        languages: set[str] = set()
        for service_data in by_service.values():
            for lang in service_data.get("languages", []):
                languages.add(lang.lower())
        if languages:
            return sorted(languages)
    except (json.JSONDecodeError, KeyError):
        pass
    return None


def _detect_iac(repo_path: Path) -> bool:
    for pattern in ("Dockerfile", "Dockerfile.*"):
        if list(repo_path.glob(pattern)):
            return True
    for tf_file in repo_path.rglob("*.tf"):
        if ".git" not in tf_file.parts:
            return True
    for iac_dir in IAC_DIRS:
        candidate = repo_path / iac_dir
        if candidate.is_dir():
            yaml_files = list(candidate.glob("*.yaml")) + list(candidate.glob("*.yml"))
            if yaml_files:
                return True
    return False


def _detect_dotnet(repo_path: Path) -> bool:
    return any(repo_path.rglob("*.csproj"))


def _detect_c_cpp(repo_path: Path) -> bool:
    cmake = repo_path / "CMakeLists.txt"
    if cmake.exists():
        return True
    c_files = list(repo_path.glob("*.c")) + list(repo_path.glob("*.h")) + list(repo_path.glob("*.cpp"))
    return bool(c_files)


def _detect_tsconfig(repo_path: Path) -> bool:
    return (repo_path / "tsconfig.json").exists()


def detect_stack(repo_path: Path, config_dir: str = ".claude") -> dict:
    languages: set[str] = set()
    lockfiles: list[str] = []

    framework_languages = _detect_from_framework_config(repo_path, config_dir)
    if framework_languages:
        languages.update(framework_languages)
        return {"languages": sorted(languages), "lockfiles": [], "source": "framework-config"}

    for filename, language in MANIFEST_LANGUAGE_MAP.items():
        candidate = repo_path / filename
        if candidate.exists():
            if language == "javascript" and (repo_path / "tsconfig.json").exists():
                languages.add("typescript")
            else:
                languages.add(language)
            lockfiles.append(filename)

    for req_glob in repo_path.glob("requirements*.txt"):
        if "python" not in languages:
            languages.add("python")
        lockfile_name = req_glob.name
        if lockfile_name not in lockfiles:
            lockfiles.append(lockfile_name)

    if _detect_dotnet(repo_path):
        languages.add("dotnet")
    if _detect_c_cpp(repo_path):
        languages.add("c_cpp")
    if _detect_iac(repo_path):
        languages.add("iac")

    if "javascript" in languages and _detect_tsconfig(repo_path):
        languages.discard("javascript")
        languages.add("typescript")

    return {"languages": sorted(languages), "lockfiles": sorted(lockfiles), "source": "local-detection"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect the technology stack of a repository by inspecting manifest markers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--repo-path", required=True, help="Absolute path to the repository root")
    parser.add_argument("--out-dir", required=True, help="Absolute path to the output directory")
    parser.add_argument(
        "--config-dir",
        default=".claude",
        help="Provider config directory under the repo root that contains framework-config.json (default: .claude)",
    )
    args = parser.parse_args()

    repo_path = Path(args.repo_path).resolve()
    out_dir = Path(args.out_dir).resolve()

    if not repo_path.is_dir():
        print(f"ERROR: --repo-path '{repo_path}' is not a directory", file=sys.stderr)
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    result = detect_stack(repo_path, args.config_dir)

    output_path = out_dir / "stack.json"
    output_path.write_text(json.dumps(result, indent=2))

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

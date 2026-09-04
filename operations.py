from __future__ import annotations

import shutil
import stat
import os
import getpass
from dataclasses import dataclass
from pathlib import Path

import acl
import psutil
from paths import BrowserSpec, cache_targets, find_profiles


@dataclass
class Summary:
    success: int = 0
    warnings: int = 0
    errors: int = 0


def is_reparse_point(path: Path) -> bool:
    attributes = path.stat(follow_symlinks=False).st_file_attributes
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def close_processes(spec: BrowserSpec, logger) -> None:
    current_user = (os.getenv("USERDOMAIN", "") + "\\" + getpass.getuser()).casefold()
    candidates = []
    for process in psutil.process_iter(["name", "username", "exe", "cmdline"]):
        try:
            name = (process.info["name"] or "").casefold()
            username = (process.info["username"] or "").casefold()
            command = " ".join(process.info["cmdline"] or []).casefold()
            executable = (process.info["exe"] or "").casefold()
            marker_matches = not spec.process_marker or spec.process_marker.casefold() in f"{executable} {command}"
            if name == spec.process_name.casefold() and (
                username == current_user or username.endswith("\\" + getpass.getuser().casefold())
            ) and marker_matches:
                candidates.append(process)
        except (psutil.AccessDenied, psutil.NoSuchProcess, TypeError):
            continue

    if not candidates:
        logger.info("%s was not running", spec.label)
        return

    for process in candidates:
        try:
            process.terminate()
        except (psutil.AccessDenied, psutil.NoSuchProcess) as exc:
            raise RuntimeError(f"Could not close {spec.label}") from exc
    _, alive = psutil.wait_procs(candidates, timeout=5)
    for process in alive:
        try:
            process.kill()
        except (psutil.AccessDenied, psutil.NoSuchProcess) as exc:
            raise RuntimeError(f"Could not close {spec.label}") from exc
    _, still_alive = psutil.wait_procs(alive, timeout=5)
    if still_alive:
        raise RuntimeError(f"Could not close {spec.label}: process is still running")
    logger.info("Closed %s processes", spec.label)


def clean_folder(folder: Path, logger) -> list[str]:
    failures = []
    for item in list(folder.iterdir()):
        try:
            if is_reparse_point(item) or item.is_symlink() or item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        except (FileNotFoundError, PermissionError, OSError) as exc:
            failures.append(f"{item}: {exc}")
            logger.warning("Could not remove %s: %s", item, exc)
    return failures


def existing_tree(root: Path):
    yield root
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        directories[:] = [
            name
            for name in directories
            if not is_reparse_point(Path(current) / name)
        ]
        for name in directories + files:
            yield Path(current) / name


def run_operation(
    mode: str,
    spec: BrowserSpec,
    logger,
    close_browser: bool = True,
    clean_before_lock: bool = True,
) -> Summary:
    summary = Summary()
    if mode not in {"lock", "unlock"}:
        raise ValueError(f"Unknown operation: {mode}")
    if close_browser:
        close_processes(spec, logger)

    logger.info("Browser data root: %s", spec.data_root)
    profiles = find_profiles(spec)
    if not profiles:
        logger.warning("No %s profiles found", spec.label)
        summary.warnings += 1
        return summary

    for profile in profiles:
        logger.info("Profile: %s", profile.name)
        for folder in cache_targets(spec, profile):
            try:
                if mode == "lock":
                    folder.mkdir(parents=True, exist_ok=True)
                    if is_reparse_point(folder):
                        raise RuntimeError("Refusing to process a reparse-point cache folder")
                    acl.remove_write_denies(folder)
                    failures = clean_folder(folder, logger) if clean_before_lock else []
                    acl.add_write_deny(folder)
                    if not acl.is_write_blocked(folder):
                        raise RuntimeError("ACL verification failed")
                    if failures:
                        summary.warnings += 1
                        logger.warning("Locked with cleanup warnings: %s", folder)
                    else:
                        summary.success += 1
                        logger.info("Locked%s: %s", " after cleanup" if clean_before_lock else "", folder)
                elif mode == "unlock":
                    if not folder.exists():
                        summary.success += 1
                        logger.info("Not found, skipped: %s", folder)
                        continue
                    if is_reparse_point(folder):
                        raise RuntimeError("Refusing to process a reparse-point cache folder")
                    removed = False
                    tree_warnings = 0
                    for item in existing_tree(folder):
                        try:
                            removed = acl.remove_write_denies(item) or removed
                        except (PermissionError, OSError, RuntimeError) as exc:
                            tree_warnings += 1
                            logger.warning("Could not remove ACL from %s: %s", item, exc)
                    if acl.is_write_blocked(folder):
                        raise RuntimeError("ACL verification failed")
                    if tree_warnings:
                        summary.warnings += 1
                    else:
                        summary.success += 1
                    logger.info("Unlocked%s: %s", " (rule not found)" if not removed else "", folder)
                else:
                    raise ValueError(f"Unknown operation: {mode}")
            except (PermissionError, OSError, RuntimeError) as exc:
                summary.errors += 1
                logger.error("Failed %s: %s: %s", mode, folder, exc)
    return summary


def collect_status(spec: BrowserSpec, logger) -> list[tuple[str, str, str]]:
    rows = []
    for profile in find_profiles(spec):
        for folder in cache_targets(spec, profile):
            if not folder.exists():
                status = "Не найдена"
            else:
                try:
                    status = "Заблокирована" if acl.is_write_blocked(folder) else "Разблокирована"
                except (PermissionError, OSError, RuntimeError):
                    status = "Ошибка доступа"
            rows.append((profile.name, folder.name, status))
    logger.info("Status refreshed: %d rows", len(rows))
    return rows
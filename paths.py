from __future__ import annotations

import ctypes
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BrowserSpec:
    key: str
    label: str
    data_root: Path
    process_name: str
    profile_layout: str
    cache_names: tuple[str, ...]
    cache_root: Path | None = None
    process_marker: str | None = None


PROFILE_PATTERN = re.compile(r"^Profile \d+$", re.IGNORECASE)
FIREFOX_PROFILE_PATTERN = re.compile(
    r"^.+\.(?:default|dev-edition-default)(?:-[a-z0-9-]+)?$",
    re.IGNORECASE,
)


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = path.stat(follow_symlinks=False).st_file_attributes
    except (FileNotFoundError, OSError):
        return True
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _known_folder(csidl: int) -> Path | None:
    if os.name != "nt":
        return None
    try:
        buffer = ctypes.create_unicode_buffer(260)
        result = ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buffer)
        if result == 0 and buffer.value:
            return Path(buffer.value)
    except (AttributeError, OSError):
        return None
    return None


def chrome_user_data() -> Path:
    local_appdata = _known_folder(0x001C)
    local_appdata = str(local_appdata) if local_appdata else None
    local_appdata = local_appdata or os.getenv("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "Google" / "Chrome" / "User Data"
    return Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data"


def local_appdata() -> Path:
    return _known_folder(0x001C) or Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")


def roaming_appdata() -> Path:
    return _known_folder(0x001A) or Path(os.getenv("APPDATA") or Path.home() / "AppData" / "Roaming")


def browser_specs() -> tuple[BrowserSpec, ...]:
    chromium_cache = ("Cache", "Code Cache", "GPUCache", "Service Worker\\CacheStorage")
    local = local_appdata()
    return (
        BrowserSpec("chrome", "Google Chrome", local / "Google" / "Chrome" / "User Data", "chrome.exe", "chromium", chromium_cache),
        BrowserSpec("edge", "Microsoft Edge", local / "Microsoft" / "Edge" / "User Data", "msedge.exe", "chromium", chromium_cache),
        BrowserSpec("brave", "Brave", local / "BraveSoftware" / "Brave-Browser" / "User Data", "brave.exe", "chromium", chromium_cache),
        BrowserSpec("vivaldi", "Vivaldi", local / "Vivaldi" / "User Data", "vivaldi.exe", "chromium", chromium_cache),
        BrowserSpec("chromium", "Chromium", local / "Chromium" / "User Data", "chromium.exe", "chromium", chromium_cache),
        BrowserSpec("yandex", "Yandex Browser", local / "Yandex" / "YandexBrowser" / "User Data", "browser.exe", "chromium", chromium_cache, process_marker="yandex"),
        BrowserSpec(
            "firefox",
            "Mozilla Firefox",
            roaming_appdata() / "Mozilla" / "Firefox" / "Profiles",
            "firefox.exe",
            "firefox",
            ("cache2",),
            local / "Mozilla" / "Firefox" / "Profiles",
        ),
        BrowserSpec("opera", "Opera", roaming_appdata() / "Opera Software" / "Opera Stable", "opera.exe", "single", chromium_cache),
    )


def find_profiles(spec: BrowserSpec) -> list[Path]:
    root = spec.data_root
    if not root.is_dir() or _is_reparse_point(root):
        return []
    if spec.profile_layout == "single":
        return [root]
    pattern = PROFILE_PATTERN if spec.profile_layout == "chromium" else FIREFOX_PROFILE_PATTERN
    profiles = [
        item
        for item in root.iterdir()
        if item.is_dir() and not _is_reparse_point(item)
        and (item.name.lower() == "default" or pattern.match(item.name))
    ]
    return sorted(profiles, key=lambda item: (item.name.lower() != "default", item.name.lower()))


def cache_targets(spec: BrowserSpec, profile: Path) -> list[Path]:
    cache_profile = spec.cache_root / profile.name if spec.cache_root else profile
    return [cache_profile / name for name in spec.cache_names]
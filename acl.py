from __future__ import annotations

from pathlib import Path

try:
    import ntsecuritycon
    import win32security
except ImportError as exc:
    ntsecuritycon = None
    win32security = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


EVERYONE_SID_TEXT = "S-1-1-0"


def _require_pywin32() -> None:
    if _IMPORT_ERROR is not None:
        raise RuntimeError("pywin32 is required for Windows ACL operations") from _IMPORT_ERROR


def _deny_mask() -> int:
    _require_pywin32()
    return (
        ntsecuritycon.FILE_WRITE_DATA
        | ntsecuritycon.FILE_APPEND_DATA
        | ntsecuritycon.FILE_WRITE_ATTRIBUTES
        | ntsecuritycon.FILE_WRITE_EA
        | ntsecuritycon.DELETE
    )


def _same_sid(left, right) -> bool:
    return (
        win32security.ConvertSidToStringSid(left)
        == win32security.ConvertSidToStringSid(right)
    )


def _matching_deny_indices(dacl, everyone_sid) -> list[int]:
    indices = []
    for index in range(dacl.GetAceCount()):
        ace = dacl.GetAce(index)
        if len(ace) != 3:
            continue
        header, access_mask, sid = ace
        if not isinstance(header, tuple) or len(header) != 2:
            continue
        ace_type, _ace_flags = header
        if (
            ace_type == win32security.ACCESS_DENIED_ACE_TYPE
            and _same_sid(sid, everyone_sid)
            and access_mask & _deny_mask()
        ):
            indices.append(index)
    return indices


def _get_dacl(path: Path):
    _require_pywin32()
    security_descriptor = win32security.GetNamedSecurityInfo(
        str(path),
        win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION,
    )
    dacl = security_descriptor.GetSecurityDescriptorDacl()
    return dacl


def _set_dacl(path: Path, dacl) -> None:
    win32security.SetNamedSecurityInfo(
        str(path),
        win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION,
        None,
        None,
        dacl,
        None,
    )


def remove_write_denies(path: Path) -> bool:
    """Remove matching Everyone deny ACEs and return whether anything changed."""
    dacl = _get_dacl(path)
    if dacl is None:
        return False
    everyone_sid = win32security.ConvertStringSidToSid(EVERYONE_SID_TEXT)
    indices = _matching_deny_indices(dacl, everyone_sid)
    for index in reversed(indices):
        dacl.DeleteAce(index)
    if indices:
        _set_dacl(path, dacl)
    return bool(indices)


def add_write_deny(path: Path) -> None:
    dacl = _get_dacl(path)
    if dacl is None:
        raise RuntimeError("Cannot safely modify a NULL DACL")
    everyone_sid = win32security.ConvertStringSidToSid(EVERYONE_SID_TEXT)
    for index in reversed(_matching_deny_indices(dacl, everyone_sid)):
        dacl.DeleteAce(index)
    dacl.AddAccessDeniedAceEx(
        win32security.ACL_REVISION,
        ntsecuritycon.CONTAINER_INHERIT_ACE | ntsecuritycon.OBJECT_INHERIT_ACE,
        _deny_mask(),
        everyone_sid,
    )
    _set_dacl(path, dacl)


def is_write_blocked(path: Path) -> bool:
    dacl = _get_dacl(path)
    if dacl is None:
        return False
    everyone_sid = win32security.ConvertStringSidToSid(EVERYONE_SID_TEXT)
    return bool(_matching_deny_indices(dacl, everyone_sid))
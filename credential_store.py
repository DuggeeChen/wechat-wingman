# -*- coding: utf-8 -*-
"""Small Windows Credential Manager wrapper. Secrets never touch config files."""
import ctypes
import ctypes.wintypes as wt
import os


CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
MAX_BLOB_BYTES = 2560


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wt.DWORD), ("dwHighDateTime", wt.DWORD)]


class _CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags", wt.DWORD),
        ("Type", wt.DWORD),
        ("TargetName", wt.LPWSTR),
        ("Comment", wt.LPWSTR),
        ("LastWritten", _FILETIME),
        ("CredentialBlobSize", wt.DWORD),
        ("CredentialBlob", ctypes.c_void_p),
        ("Persist", wt.DWORD),
        ("AttributeCount", wt.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wt.LPWSTR),
        ("UserName", wt.LPWSTR),
    ]


def _api():
    if os.name != "nt":
        return None
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi.CredReadW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD,
                                 ctypes.POINTER(ctypes.POINTER(_CREDENTIAL))]
    advapi.CredReadW.restype = wt.BOOL
    advapi.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIAL), wt.DWORD]
    advapi.CredWriteW.restype = wt.BOOL
    advapi.CredDeleteW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD]
    advapi.CredDeleteW.restype = wt.BOOL
    advapi.CredFree.argtypes = [ctypes.c_void_p]
    advapi.CredFree.restype = None
    return advapi


def read_secret(target):
    """Return a generic credential secret, or an empty string when absent."""
    if not target:
        return ""
    advapi = _api()
    if advapi is None:
        return ""
    pointer = ctypes.POINTER(_CREDENTIAL)()
    if not advapi.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
        return ""
    try:
        cred = pointer.contents
        if not cred.CredentialBlob or not cred.CredentialBlobSize:
            return ""
        raw = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
        try:
            return raw.decode("utf-16-le").rstrip("\x00").strip()
        except UnicodeDecodeError:
            return raw.decode("utf-8", errors="replace").rstrip("\x00").strip()
    finally:
        advapi.CredFree(pointer)


def write_secret(target, secret, comment="微信军师 API 凭据"):
    """Create or replace a generic credential for the current Windows user."""
    target = str(target or "").strip()
    secret = str(secret or "").strip()
    if not target or not secret:
        raise ValueError("凭据名称和 API Key 都不能为空")
    advapi = _api()
    if advapi is None:
        raise OSError("仅支持 Windows 凭据管理器")
    raw = secret.encode("utf-16-le")
    if len(raw) > MAX_BLOB_BYTES:
        raise ValueError("API Key 太长，无法写入 Windows 凭据管理器")
    blob = ctypes.create_string_buffer(raw, len(raw))
    cred = _CREDENTIAL()
    cred.Type = CRED_TYPE_GENERIC
    cred.TargetName = target
    cred.Comment = comment
    cred.CredentialBlobSize = len(raw)
    cred.CredentialBlob = ctypes.cast(blob, ctypes.c_void_p)
    cred.Persist = CRED_PERSIST_LOCAL_MACHINE
    cred.UserName = os.environ.get("USERNAME", "微信军师")
    if not advapi.CredWriteW(ctypes.byref(cred), 0):
        error = ctypes.get_last_error()
        raise ctypes.WinError(error)
    return True


def delete_secret(target):
    """Delete a generic credential. Missing credentials count as success."""
    advapi = _api()
    if advapi is None:
        return False
    if advapi.CredDeleteW(str(target), CRED_TYPE_GENERIC, 0):
        return True
    error = ctypes.get_last_error()
    if error == 1168:  # ERROR_NOT_FOUND
        return True
    raise ctypes.WinError(error)

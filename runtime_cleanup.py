"""Delete only named disposable files in the app's writable data directory."""
import stat
from pathlib import Path


TEMP_NAMES = ("debug_last.png", "wx_helper.log", "wx_helper.log.1")


def clean_temporary_data(data_dir):
    root = Path(data_dir).resolve()
    result = {"removed": [], "bytes": 0, "failed": []}
    for name in TEMP_NAMES:
        path = root / name
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            result["failed"].append(name)
            continue
        try:
            # No recursive traversal, globs or deleting link targets. A directory
            # or link using a disposable filename is left for manual inspection.
            if not stat.S_ISREG(info.st_mode) or path.is_symlink() or path.resolve().parent != root:
                result["failed"].append(name)
                continue
            path.unlink()
            result["removed"].append(name)
            result["bytes"] += info.st_size
        except FileNotFoundError:
            pass  # Rotation or another cleanup may have removed it already.
        except OSError:
            result["failed"].append(name)
    return result

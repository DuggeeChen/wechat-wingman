# -*- coding: utf-8 -*-
"""Resource and writable-data locations for source and packaged builds."""
import os
import sys


APP_FOLDER_NAME = "微信军师"
FROZEN = bool(getattr(sys, "frozen", False))


def _resource_dir():
    if FROZEN:
        return os.path.abspath(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
    return os.path.dirname(os.path.abspath(__file__))


def _data_dir():
    # The override is intentionally undocumented for normal users; it makes clean-room
    # package tests possible without touching a real profile.
    override = os.environ.get("WX_HELPER_DATA_DIR", "").strip()
    if override:
        return os.path.abspath(override)
    if not FROZEN:
        # Preserve the existing source checkout behaviour for current users.
        return _resource_dir()
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if not local:
        local = os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(local, APP_FOLDER_NAME)


RESOURCE_DIR = _resource_dir()
DATA_DIR = _data_dir()
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
LOG_PATH = os.path.join(DATA_DIR, "wx_helper.log")
UI_STATE_PATH = os.path.join(DATA_DIR, "ui_state.json")
PROFILE_DIR = os.path.join(DATA_DIR, "profiles")


def resource_path(*parts):
    return os.path.join(RESOURCE_DIR, *parts)


def data_path(*parts):
    return os.path.join(DATA_DIR, *parts)


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)
    return DATA_DIR

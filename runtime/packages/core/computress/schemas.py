from __future__ import annotations
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, Any, List, Optional

class VddStatus(IntEnum):
    IDLE = 0
    BUSY = 1
    READY = 2
    BLOCKED = 3
    ERROR = 4

class VddCommand(IntEnum):
    NOOP = 0
    OBSERVE = 1
    MOUSE_MOVE = 2
    MOUSE_CLICK = 3
    KEY_PRESS = 4
    TYPE_TEXT = 5
    CLIPBOARD_SET = 6
    CLIPBOARD_GET = 7
    WINDOW_FOCUS = 8
    APP_LAUNCH = 9
    BROWSER_NAVIGATE = 10
    BROWSER_QUERY = 11
    FILE_IMPORT = 12
    FILE_EXPORT = 13
    SNAPSHOT = 14
    RESTORE = 15
    ABORT = 16

@dataclass
class DesktopObservation:
    frame_base64: Optional[str] = None
    text_content: Optional[str] = None
    accessibility_tree: Optional[Dict[str, Any]] = None
    url: Optional[str] = None
    title: Optional[str] = None

@dataclass
class DesktopResult:
    status: VddStatus
    result_code: int
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

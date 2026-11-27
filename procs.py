"""All running processes in one system call (a few milliseconds).

psutil opens every process separately, which took 3 seconds while a game was running. The same numbers come from
NtQuerySystemInformation at once: name, memory and processor time.
"""
from __future__ import annotations

import ctypes
import os
import threading
import time
from ctypes import wintypes


class _Info(ctypes.Structure):
    _fields_ = [("next", wintypes.ULONG), ("threads", wintypes.ULONG), ("private", ctypes.c_longlong), ("_a", wintypes.ULONG * 2),
                ("cycles", ctypes.c_ulonglong), ("create", ctypes.c_longlong), ("user", ctypes.c_longlong), ("kernel", ctypes.c_longlong),
                ("name_len", wintypes.USHORT), ("name_max", wintypes.USHORT), ("name", ctypes.c_void_p), ("prio", wintypes.LONG),
                ("pid", ctypes.c_void_p), ("parent", ctypes.c_void_p), ("handles", wintypes.ULONG), ("session", wintypes.ULONG),
                ("key", ctypes.c_void_p), ("peak_virtual", ctypes.c_size_t), ("virtual", ctypes.c_size_t), ("faults", wintypes.ULONG),
                ("peak_ws", ctypes.c_size_t), ("ws", ctypes.c_size_t)]


_SIZE = [1 << 20]
_LAST: dict = {"at": 0.0, "rows": []}
_PREV: dict[int, tuple[float, int]] = {}
_LOCK = threading.Lock()


def _read() -> list[dict]:
    need = wintypes.ULONG()
    while True:
        buf = ctypes.create_string_buffer(_SIZE[0])
        st = ctypes.windll.ntdll.NtQuerySystemInformation(5, buf, _SIZE[0], ctypes.byref(need)) & 0xFFFFFFFF
        if st == 0:
            break
        if st != 0xC0000004 or _SIZE[0] > 1 << 26:        # anything but «the buffer is too small»
            raise OSError(f"NtQuerySystemInformation {st:#x}")
        _SIZE[0] = max(_SIZE[0] * 2, need.value + 65536)
    rows, off, base = [], 0, ctypes.addressof(buf)
    while True:
        i = _Info.from_address(base + off)
        name = ctypes.wstring_at(i.name, i.name_len // 2) if i.name else ""
        rows.append({"pid": i.pid or 0, "name": name, "mem": i.ws / 2**20, "time": i.user + i.kernel, "start": i.create})
        if not i.next:
            return rows
        off += i.next


def snapshot(max_age: float = 2.0) -> list[dict]:
    """[{pid, name, mem (MB), cpu (% of the whole PC since the previous look)}]"""
    with _LOCK:
        now = time.time()
        if _LAST["rows"] and now - _LAST["at"] < max_age:
            return _LAST["rows"]
        rows, n = _read(), os.cpu_count() or 1
        prev_at, took = _LAST["at"], now - _LAST["at"]
        for r in rows:
            before = _PREV.get(r["pid"])
            same = before and before[0] == r["start"] and prev_at
            r["cpu"] = max(0.0, (r["time"] - before[1]) / 1e7 / took / n * 100) if same else 0.0
        _PREV.clear()
        _PREV.update({r["pid"]: (r["start"], r["time"]) for r in rows})
        _LAST.update(at=now, rows=rows)
        return rows

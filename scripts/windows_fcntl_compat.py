from __future__ import annotations

import os
import sys
import types


def build_fcntl_module():
    module = types.ModuleType('fcntl')
    module.LOCK_SH = 1
    module.LOCK_EX = 2
    module.LOCK_NB = 4
    module.LOCK_UN = 8

    def flock(fd: int, operation: int) -> None:
        if os.name != 'nt':
            raise RuntimeError('Windows fcntl compatibility module used on non-Windows host')
        import msvcrt
        pos = os.lseek(fd, 0, os.SEEK_CUR)
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            if operation & module.LOCK_UN:
                mode = msvcrt.LK_UNLCK
            elif operation & module.LOCK_EX:
                mode = msvcrt.LK_NBLCK if operation & module.LOCK_NB else msvcrt.LK_LOCK
            elif operation & module.LOCK_SH:
                mode = msvcrt.LK_NBRLCK if operation & module.LOCK_NB else msvcrt.LK_RLCK
            else:
                raise ValueError(f'unsupported flock operation: {operation}')
            # msvcrt.locking requires a positive byte range. Lock byte zero only;
            # this matches the repository's advisory lock-file usage.
            try:
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b'\0')
                    os.fsync(fd)
                    os.lseek(fd, 0, os.SEEK_SET)
            except OSError:
                pass
            msvcrt.locking(fd, mode, 1)
        finally:
            os.lseek(fd, pos, os.SEEK_SET)

    module.flock = flock
    return module


def install_fcntl_compat() -> None:
    if os.name == 'nt' and 'fcntl' not in sys.modules:
        sys.modules['fcntl'] = build_fcntl_module()

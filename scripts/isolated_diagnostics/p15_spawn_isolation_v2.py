"""Darwin-only posix_spawn for the synthetic T102 process boundary.

This is not a real-provider transport.  Spawn only explicit descriptors and a
minimal environment; never fall back to fork if the platform is unsupported.
"""

import ctypes
import os
import signal
import subprocess
import sys
from typing import Any, cast

VERSION = "darwin-posix-spawn-cloexec-v2-offline"
_CLOEXEC_DEFAULT = 0x4000
_SETSID = 0x0400
_SETSIGDEF = 0x0004


def _checked(code: int) -> None:
    if code:
        raise OSError(code, os.strerror(code))


class SpawnOnlyPopen(subprocess.Popen[bytes]):
    """Use Popen's pipe management but never its fork or fallback paths.

    POSIX_SPAWN_CLOEXEC_DEFAULT atomically closes descriptors not explicitly
    listed in file actions; unlike scanning open fds it cannot race another
    thread opening an inheritable descriptor. This adapter is intentionally
    pinned to the project's CPython 3.11 on Darwin.
    """

    def _execute_child(
        self, args: Any, executable: Any, preexec_fn: Any, close_fds: Any,
        pass_fds: Any, cwd: Any, env: Any, startupinfo: Any, creationflags: Any,
        shell: Any, p2cread: Any, p2cwrite: Any, c2pread: Any, c2pwrite: Any,
        errread: Any, errwrite: Any, restore_signals: Any, gid: Any, gids: Any,
        uid: Any, umask: Any, start_new_session: Any, process_group: Any,
    ) -> None:
        if (
            sys.platform != "darwin" or sys.version_info[:2] != (3, 11)
            or preexec_fn is not None or not close_fds or cwd is not None
            or env is None or startupinfo is not None or creationflags or shell
            or type(start_new_session) is not bool or process_group != -1
            or gid is not None or gids is not None or uid is not None or umask != -1
            or not restore_signals
        ):
            raise OSError("unsupported spawn policy")
        argv = list(args)
        path = executable or argv[0]
        if not os.path.isabs(path):
            raise OSError("absolute executable required")
        encoded_args = [os.fsencode(item) for item in argv]
        encoded_env = [os.fsencode(k) + b"=" + os.fsencode(v) for k, v in env.items()]
        if any(b"\0" in item for item in encoded_args + encoded_env):
            raise ValueError("NUL in spawn arguments")
        if any("=" in k for k in env):
            raise ValueError("invalid spawn environment")
        argument_vector = (ctypes.c_char_p * (len(encoded_args) + 1))(*encoded_args, None)
        environment_vector = (ctypes.c_char_p * (len(encoded_env) + 1))(*encoded_env, None)
        lib = ctypes.CDLL(None)
        actions, attr = ctypes.c_void_p(), ctypes.c_void_p()
        _checked(lib.posix_spawn_file_actions_init(ctypes.byref(actions)))
        try:
            _checked(lib.posix_spawnattr_init(ctypes.byref(attr)))
            try:
                flags = _CLOEXEC_DEFAULT | _SETSIGDEF | (_SETSID if start_new_session else 0)
                _checked(lib.posix_spawnattr_setflags(ctypes.byref(attr), ctypes.c_short(flags)))
                sigset = ctypes.c_uint32()
                _checked(lib.sigemptyset(ctypes.byref(sigset)))
                for name in ("SIGPIPE", "SIGXFZ", "SIGXFSZ"):
                    signum = getattr(signal, name, None)
                    if signum is not None:
                        _checked(lib.sigaddset(ctypes.byref(sigset), signum))
                _checked(lib.posix_spawnattr_setsigdefault(ctypes.byref(attr), ctypes.byref(sigset)))
                for source, target in ((p2cread, 0), (c2pwrite, 1), (errwrite, 2)):
                    if source == -1:
                        _checked(lib.posix_spawn_file_actions_addinherit_np(ctypes.byref(actions), target))
                    else:
                        _checked(lib.posix_spawn_file_actions_adddup2(ctypes.byref(actions), source, target))
                for fd in pass_fds:
                    if fd <= 2:
                        raise OSError("invalid extra descriptor")
                    _checked(lib.posix_spawn_file_actions_addinherit_np(ctypes.byref(actions), fd))
                pid = ctypes.c_int()
                _checked(lib.posix_spawn(
                    ctypes.byref(pid), os.fsencode(path), ctypes.byref(actions),
                    ctypes.byref(attr), argument_vector, environment_vector,
                ))
                self.pid = pid.value
                self._child_created = True
            finally:
                lib.posix_spawnattr_destroy(ctypes.byref(attr))
        finally:
            lib.posix_spawn_file_actions_destroy(ctypes.byref(actions))
        cast(Any, self)._close_pipe_fds(p2cread, p2cwrite, c2pread, c2pwrite, errread, errwrite)

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

CREATE_SUSPENDED = 0x00000004


class _ThreadEntry32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
        ("th32ThreadID", wintypes.DWORD), ("th32OwnerProcessID", wintypes.DWORD),
        ("tpBasePri", wintypes.LONG), ("tpDeltaPri", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
    ]


def assign_job_and_resume(process):
    """Atomically contain a CREATE_SUSPENDED Windows child, then resume it."""
    if os.name != "nt":
        return None
    job = None
    close_handle = None
    try:
        if not hasattr(process, "_handle"):
            raise RuntimeError("Windows process handle is unavailable")

        import win32api
        import win32job
        import win32process

        close_handle = win32api.CloseHandle
        job = win32job.CreateJobObject(None, "")
        info = win32job.QueryInformationJobObject(
            job, win32job.JobObjectExtendedLimitInformation
        )
        info["BasicLimitInformation"]["LimitFlags"] |= (
            win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        win32job.SetInformationJobObject(
            job, win32job.JobObjectExtendedLimitInformation, info
        )
        win32job.AssignProcessToJobObject(job, int(process._handle))
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ThreadEntry32)]
        kernel.Thread32First.restype = wintypes.BOOL
        kernel.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ThreadEntry32)]
        kernel.Thread32Next.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        snapshot = kernel.CreateToolhelp32Snapshot(0x00000004, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            raise OSError(ctypes.get_last_error(), "thread snapshot failed")
        try:
            entry = _ThreadEntry32()
            entry.dwSize = ctypes.sizeof(entry)
            found = kernel.Thread32First(snapshot, ctypes.byref(entry))
            while found and entry.th32OwnerProcessID != process.pid:
                found = kernel.Thread32Next(snapshot, ctypes.byref(entry))
            if not found:
                raise OSError("suspended process thread not found")
            thread = win32api.OpenThread(0x0002, False, entry.th32ThreadID)
            try:
                if win32process.ResumeThread(thread) == -1:
                    raise OSError("suspended process could not be resumed")
            finally:
                win32api.CloseHandle(thread)
        finally:
            kernel.CloseHandle(snapshot)
        return job
    except BaseException:
        if job is not None and close_handle is not None:
            try:
                close_handle(job)
            except BaseException:
                pass
        try:
            process.kill()
        except BaseException:
            pass
        try:
            process.wait(timeout=2)
        except BaseException:
            pass
        for stream in (
            getattr(process, "stdin", None),
            getattr(process, "stdout", None),
            getattr(process, "stderr", None),
        ):
            if stream is not None:
                try:
                    stream.close()
                except BaseException:
                    pass
        raise


def close_job(job) -> None:
    if job is not None:
        import win32api

        win32api.CloseHandle(job)

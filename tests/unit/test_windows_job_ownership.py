"""Handle-ownership tests: all Windows calls and process operations are mocked."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pex_protocol import windows_job


@pytest.mark.parametrize("thread_owner", [0, 999, 42])
def test_opened_thread_owner_is_checked_before_resume(monkeypatch, thread_owner):
    process = Mock(pid=42, _handle=123)
    job = 701
    thread = 702
    api = SimpleNamespace(CloseHandle=Mock(), OpenThread=Mock(return_value=thread))
    jobs = SimpleNamespace(
        CreateJobObject=Mock(return_value=job),
        QueryInformationJobObject=Mock(return_value={"BasicLimitInformation": {"LimitFlags": 0}}),
        SetInformationJobObject=Mock(), AssignProcessToJobObject=Mock(),
        JobObjectExtendedLimitInformation=9, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE=8192,
    )
    processes = SimpleNamespace(ResumeThread=Mock(return_value=1))

    def query_owner(_thread):
        processes.ResumeThread.assert_not_called()
        return thread_owner

    def first(_snapshot, pointer):
        pointer._obj.th32OwnerProcessID = process.pid
        pointer._obj.th32ThreadID = 88
        return True

    kernel = SimpleNamespace(
        CreateToolhelp32Snapshot=Mock(return_value=703),
        Thread32First=Mock(side_effect=first), Thread32Next=Mock(return_value=False),
        CloseHandle=Mock(return_value=True),
        GetProcessIdOfThread=Mock(side_effect=query_owner),
    )
    monkeypatch.setattr(windows_job, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(windows_job.ctypes, "WinDLL", Mock(return_value=kernel), raising=False)
    for name, module in (("win32api", api), ("win32job", jobs), ("win32process", processes)):
        monkeypatch.setitem(sys.modules, name, module)

    if thread_owner == process.pid:
        assert windows_job.assign_job_and_resume(process) == job
        processes.ResumeThread.assert_called_once_with(thread)
        process.kill.assert_not_called()
        assert api.CloseHandle.call_args_list == [((thread,),)]
    else:
        with pytest.raises(OSError, match="thread ownership"):
            windows_job.assign_job_and_resume(process)
        processes.ResumeThread.assert_not_called()
        process.kill.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=2)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close.assert_called_once_with()
        assert api.CloseHandle.call_args_list == [((thread,),), ((job,),)]
    kernel.GetProcessIdOfThread.assert_called_once_with(thread)
    kernel.CloseHandle.assert_called_once_with(703)
    api.OpenThread.assert_called_once_with(0x0802, False, 88)
    jobs.AssignProcessToJobObject.assert_called_once_with(job, 123)

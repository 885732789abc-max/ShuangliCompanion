"""Serialize packaging inside a CPU/memory job, preserving free system memory."""
import ctypes as C
from ctypes import wintypes as W
import msvcrt
import os
import subprocess
import sys
import time
import shutil

from guarded_editor import ROOT, K, Limits, Cpu, Startup, Process, available, checked


def main():
    for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[key] = '1'
    os.environ['PYTHONUTF8'] = '1'
    reserve = 1100
    free = available()
    if free < reserve + 250:
        print(f'Packaging deferred: {free} MB available; {reserve + 250} MB needed.', flush=True)
        return 8
    budget = min(600, free - reserve)
    job = K.CreateJobObjectW(None, None);checked(job)
    proc = Process()
    try:
        info = Limits();info.basic.flags = 0x2000 | 0x200
        info.job_memory = budget * 1048576
        checked(K.SetInformationJobObject(job, 9, C.byref(info), C.sizeof(info)))
        cpu = Cpu(1 | 4, 2000)
        checked(K.SetInformationJobObject(job, 15, C.byref(cpu), C.sizeof(cpu)))
        log_path = ROOT / 'build/packaging.log';log_path.parent.mkdir(exist_ok=True)
        with log_path.open('w', encoding='utf-8') as log:
            handle = msvcrt.get_osfhandle(log.fileno());os.set_handle_inheritable(handle, True)
            startup = Startup();startup.cb = C.sizeof(startup)
            startup.flags = 0x100 | 1;startup.show = 0
            startup.stdout = startup.stderr = handle
            exe = os.path.join(os.environ['SystemRoot'], 'System32/WindowsPowerShell/v1.0/powershell.exe')
            incremental = '--incremental' in sys.argv
            if incremental:
                exe=sys.executable
                args=[exe,'-m','PyInstaller','--noconfirm','--workpath','build/incremental',
                      '--distpath','build/package-stage','ShuangliCompanion.incremental.spec']
            else:
                args=[exe, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(ROOT / 'build.ps1'), '-Worker']
            command = C.create_unicode_buffer(subprocess.list2cmdline(args))
            checked(K.CreateProcessW(exe, command, None, None, True, 0x4 | 0x4000 | 0x08000000,
                                     None, str(ROOT), C.byref(startup), C.byref(proc)))
            checked(K.AssignProcessToJobObject(job, proc.handle))
            checked(K.ResumeThread(proc.thread) != 0xffffffff)
            K.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
            K.GetExitCodeProcess.argtypes = [W.HANDLE, C.POINTER(W.DWORD)]
            print(f'Packaging budget {budget} MB; reserve {reserve} MB; log: {log_path}', flush=True)
            while K.WaitForSingleObject(proc.handle, 2000) == 258:
                if available() < reserve:
                    K.TerminateJobObject(job, 9)
                    print('Packaging stopped to preserve the memory reserve.', flush=True)
                    return 9
            code = W.DWORD();checked(K.GetExitCodeProcess(proc.handle, C.byref(code)))
            if code.value==0 and incremental:
                target=ROOT/'dist/ShuangliCompanion'
                if not (target/'_internal/python312.dll').is_file():
                    raise RuntimeError('Existing runtime is missing; use a full build.')
                files=[(ROOT/'build/package-stage/ShuangliCompanion/ShuangliCompanion.exe',target/'ShuangliCompanion.exe'),
                       (ROOT/'assets/default-pack.json',target/'_internal/assets/default-pack.json'),
                       (ROOT/'assets/manifest.json',target/'_internal/assets/manifest.json'),
                       (ROOT/'assets/live2d/shuangli-q/face-backing.png',target/'_internal/assets/live2d/shuangli-q/face-backing.png'),
                       (ROOT/'README.md',target/'README.md')]
                files.extend((file,target/'docs'/file.name) for file in (ROOT/'docs').iterdir() if file.is_file())
                files.extend((file,target/'_internal'/file.relative_to(ROOT)) for file in (ROOT/'assets/poses').rglob('*') if file.is_file())
                files.extend((file,target/'_internal'/file.relative_to(ROOT))
                             for file in (ROOT/'assets/live2d/shuangli-q').rglob('*')
                             if file.is_file() and (file.name.startswith('shuangli-layered-alpha.')
                                or file.parent.name=='shuangli-layered-alpha.2048'
                                or file.name in ('shuangli.model3.json','neutral-backing.png','idle-rig.json')))
                for source,destination in files:
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    temporary=destination.with_name(destination.name+'.update')
                    shutil.copy2(source,temporary);os.replace(temporary,destination)
            print(f'Packaging exit: {code.value}', flush=True)
            return code.value
    finally:
        K.TerminateJobObject(job, 0)
        if proc.thread:K.CloseHandle(proc.thread)
        if proc.handle:K.CloseHandle(proc.handle)
        K.CloseHandle(job)


if __name__ == '__main__':
    sys.exit(main())

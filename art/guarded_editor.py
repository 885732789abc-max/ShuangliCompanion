"""Run this project's editor inside a Windows memory/CPU Job Object."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
K=C.WinDLL('kernel32',use_last_error=True)
class Memory(C.Structure):
    _fields_=[('length',W.DWORD),('load',W.DWORD)]+[(n,C.c_ulonglong) for n in
        ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
class Basic(C.Structure):
    _fields_=[('process_time',C.c_longlong),('job_time',C.c_longlong),('flags',W.DWORD),
        ('min_ws',C.c_size_t),('max_ws',C.c_size_t),('process_limit',W.DWORD),
        ('affinity',C.c_size_t),('priority',W.DWORD),('scheduling',W.DWORD)]
class Io(C.Structure):
    _fields_=[(n,C.c_ulonglong) for n in ('read_count','write_count','other_count','read_bytes','write_bytes','other_bytes')]
class Limits(C.Structure):
    _fields_=[('basic',Basic),('io',Io)]+[(n,C.c_size_t) for n in
        ('process_memory','job_memory','peak_process_memory','peak_job_memory')]
class Cpu(C.Structure):_fields_=[('flags',W.DWORD),('rate',W.DWORD)]
class Startup(C.Structure):
    _fields_=[('cb',W.DWORD),('reserved',W.LPWSTR),('desktop',W.LPWSTR),('title',W.LPWSTR)]+[
        (n,W.DWORD) for n in ('x','y','width','height','count_x','count_y','fill','flags')]+[
        ('show',W.WORD),('reserved_size',W.WORD),('reserved_ptr',C.c_void_p),
        ('stdin',W.HANDLE),('stdout',W.HANDLE),('stderr',W.HANDLE)]
class Process(C.Structure):
    _fields_=[('handle',W.HANDLE),('thread',W.HANDLE),('pid',W.DWORD),('tid',W.DWORD)]
K.CreateJobObjectW.restype=W.HANDLE
K.CreateJobObjectW.argtypes=[C.c_void_p,W.LPCWSTR]
K.SetInformationJobObject.argtypes=[W.HANDLE,C.c_int,C.c_void_p,W.DWORD]
K.AssignProcessToJobObject.argtypes=[W.HANDLE,W.HANDLE]
K.CreateProcessW.argtypes=[W.LPCWSTR,W.LPWSTR,C.c_void_p,C.c_void_p,W.BOOL,W.DWORD,
    C.c_void_p,W.LPCWSTR,C.POINTER(Startup),C.POINTER(Process)]
K.ResumeThread.argtypes=[W.HANDLE]
K.CloseHandle.argtypes=[W.HANDLE]
K.TerminateJobObject.argtypes=[W.HANDLE,W.UINT]
K.GlobalMemoryStatusEx.argtypes=[C.POINTER(Memory)]

def available():
    mem=Memory();mem.length=C.sizeof(mem)
    if not K.GlobalMemoryStatusEx(C.byref(mem)):raise C.WinError(C.get_last_error())
    return mem.available//1048576
def checked(ok):
    if not ok:raise C.WinError(C.get_last_error())

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--script')
    ap.add_argument('--cli',nargs=argparse.REMAINDER)
    ap.add_argument('--limit-mb',type=int,default=2300)
    ap.add_argument('--reserve-mb',type=int,default=1100)
    ap.add_argument('--minimum-mb',type=int)
    args=ap.parse_args()
    if not args.script and not args.cli:ap.error('--script or --cli is required')
    need=(args.minimum_mb or (800 if args.cli else 1400))+args.reserve_mb
    while available()<need:
        print(f'Waiting for memory: available={available()} MB; start threshold={need} MB.',flush=True)
        time.sleep(30)
    args.limit_mb=min(args.limit_mb,available()-args.reserve_mb)
    cfg=ROOT/'tools/PSD2Live-3.1.1/app/PSD2Live.cfg'
    import re
    heap=max(384,min(768 if args.cli else 1024,args.limit_mb-(350 if args.cli else 650)))
    content=cfg.read_text(encoding='utf-8-sig')
    content=re.sub(r'java-options=-Xmx\d+m',f'java-options=-Xmx{heap}m',content)
    if 'UseSerialGC' not in content:content+='\njava-options=-XX:+UseSerialGC\n'
    cfg.write_text(content,encoding='utf-8')
    print(f'Editor budget={args.limit_mb} MB; heap={heap} MB; reserve={args.reserve_mb} MB.',flush=True)
    job=K.CreateJobObjectW(None,None)
    checked(job)
    info=Limits();info.basic.flags=0x2000|0x200
    info.job_memory=args.limit_mb*1048576
    checked(K.SetInformationJobObject(job,9,C.byref(info),C.sizeof(info)))
    cpu=Cpu(1|4,2000)
    checked(K.SetInformationJobObject(job,15,C.byref(cpu),C.sizeof(cpu)))
    startup=Startup();startup.cb=C.sizeof(startup);startup.flags=1;startup.show=0
    proc=Process()
    exe=ROOT/'tools/PSD2Live-3.1.1/PSD2Live.exe'
    command=C.create_unicode_buffer(subprocess.list2cmdline([str(exe)]+(args.cli or [])))
    checked(K.CreateProcessW(str(exe),command,None,None,False,0x4|0x4000,None,
        str(exe.parent),C.byref(startup),C.byref(proc)))
    worker=None
    try:
        checked(K.AssignProcessToJobObject(job,proc.handle))
        if K.ResumeThread(proc.thread)==0xffffffff:raise C.WinError(C.get_last_error())
        if args.script:
            time.sleep(3)
            worker=subprocess.Popen([sys.executable,str(ROOT/args.script)],cwd=ROOT)
        K.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD]
        K.GetExitCodeProcess.argtypes=[W.HANDLE,C.POINTER(W.DWORD)]
        while (worker.poll() is None if worker else K.WaitForSingleObject(proc.handle,0)==258):
            free=available()
            if free<args.reserve_mb:
                print(f'Memory reserve reached ({free} MB); stopping this batch.',flush=True)
                if worker:worker.terminate()
                K.TerminateJobObject(job,9)
                return 9
            time.sleep(2)
        if worker:return worker.returncode
        code=W.DWORD();checked(K.GetExitCodeProcess(proc.handle,C.byref(code)))
        return code.value
    finally:
        if worker and worker.poll() is None:worker.terminate()
        K.TerminateJobObject(job,0)
        K.CloseHandle(proc.thread);K.CloseHandle(proc.handle);K.CloseHandle(job)

if __name__=='__main__':sys.exit(main())

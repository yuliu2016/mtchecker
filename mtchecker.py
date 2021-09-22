"""
MT2MP3 (student-made) code checker!

Checks the following:
- Code is found in the right files
- Code compiles correctly
- Code outputs correct results for certain test cases
- Code is uploaded to GitLab
"""


import ctypes
import subprocess
import os
import sys
import re
import platform
import contextlib
import shutil
import tkinter
import typing
import functools
import argparse
import asyncio
import pathlib
import time

p = platform.system()
is_windows = p == "Windows"
is_mac = p == "Darwin"
is_linux = p == "Linux"

# https://www.scivision.dev/python-detect-wsl/
is_wsl = is_linux and "Microsoft" in platform.uname()


# TKinter might not be available in Linux and WSL
try:
    from tkinter import *
    from tkinter.scrolledtext import ScrolledText
    tk_lib_available = True
except ImportError:
    tk_lib_available = False



def logE(s):
    print("Error: " + str(s))

def logI(s):
    print("Info: " + str(s))

def logP(s):
    print("Pass: " + str(s))

def logW(s):
    print("Warn: " + str(s))


def check_gcc_version():
    gcc_path = shutil.which("gcc");
    if not gcc_path:
        logE("GCC is not found. Did you install it?")
        return False
    logI(f"Found gcc at {gcc_path}")

    gccv = subprocess.run(["gcc", "--version"], capture_output=True)
    if gccv.returncode != 0:
        logE("GCC might be broken")
    
    v_line = gccv.stdout.decode().split("\n")[0].strip()
    logI(f"<{v_line}>")

    version = v_line.split(" ")[-1]

    major, minor, _ = version.split(".")
    major, minor = int(major), int(minor)

    if major < 8 or (major == 8 and minor < 1):
        logW("Your GCC version is older than the recommended version")
        return False
    return True


def check_git_version():
    git_path = shutil.which("git");
    if not git_path:
        logE("Git is not found. Did you install it?")
        return False
    logI(f"Found git at {git_path}")

    gitv = subprocess.run(["git", "--version"], capture_output=True)
    if gitv.returncode != 0:
        logE()("git might be broken")
    
    v_line = gitv.stdout.decode().split("\n")[0].strip()
    logI(f"<{v_line}>")
    return True


class ShellOut:

    def __init__(self, stdout, wrapped) -> None:
        self.stdout = stdout
        self.wrapped = wrapped

    def write(self, obj):
        if type(obj) == str:
            self.writestr(obj)
        else:
            self.writestr(str(obj))
    
    def writestr(self, s: str):
        wrapper = None

        if s.startswith("Info: "):
            s = s[6:]
            wrapper = "\033[34m"
        elif s.startswith("Warn: "):
            s = s[6:]
            wrapper = "\033[33m"
        elif s.startswith("Error: "):
            s = s[7:]
            wrapper = "\031[34m"
        
        if wrapper and self.wrapped:
            s = wrapper + s + "\033[0m"
        self.stdout.write(s)

    def flush(self):
        self.stdout.flush()


class TkOut:
    def __init__(self) -> None:
        self.window = Tk()
        self.window.title("2MP3 Checker")

        win = self.window

        frm = Frame(win)

        options = [f"Assignment {i}" for i in range(1,8)]
        svar = tkinter.StringVar(frm)
        svar.set("Assignment 1")
        self.selector = OptionMenu(frm, svar, *options)
        self.selector.pack(side=LEFT)

        options2 = ["All Questions"] + [f"Question {i}" for i in range(1,8)]
        svar2 = tkinter.StringVar(frm)
        svar2.set("All Questions")
        self.selector2 = OptionMenu(frm, svar2, *options2)
        self.selector2.pack(side=LEFT)

        self.btn2 = Button(frm, text="Open a new Folder")
        self.btn2.pack(side=LEFT)

        self.btn = Button(frm, text="Check my Code")
        self.btn.pack(side=LEFT)
        
        frm.pack()
        self.folder = Label(win, text=f"Project Folder: {os.getcwd()}")
        self.folder.pack()


        self.results = ScrolledText(self.window, width=80, height=24, selectbackground="lightgray")
        self.results.pack()
        self.results.tag_config("t_blue", foreground="blue")
        self.results.tag_config("t_yellow", foreground="yellow")
        self.results.tag_config("t_red", foreground="red")
        self.results.tag_config("t_green", foreground="green")
    
    def flush(self):
        pass

    def write(self, obj):
        if type(obj) == str:
            self.writestr(obj)
        else:
            self.writestr(str(obj))
    
    def writestr(self, s: str):
        colour = None

        if s.startswith("Info: "):
            s = s[6:]
            colour = "t_blue"
        elif s.startswith("Warn: "):
            s = s[6:]
            colour = "t_yellow"
        elif s.startswith("Error: "):
            s = s[7:]
            colour = "t_red"
        elif s.startswith("Pass: "):
            s = s[6:]
            colour = "t_green"
        
        self.results.insert(END, s, colour)


class EWrapper:
    def __init__(self, stdout, stderr) -> None:
        self.stdout = stdout
        self.stderr = stderr

    def flush(self):
        self.stdout.flush()
        self.stderr.flush()

    def write(self, obj):
        self.stdout.write(f"Error: {obj}")
        self.stderr.write(obj)

def sequential_checks(*funcs: typing.Callable[..., bool]):
    for func in funcs:
        result = func()
        if not result:
            logE(f"Stopping at check <{func.__name__}>")
            return
    logP("All checks finished")


def setup_stdio():
    using_tk = False
    new_stdout = None
    if tk_lib_available:
        try:
            using_tk = True
            new_stdout = TkOut()  # Use the graphical interface!!
        except TclError:
            pass
    
    if not using_tk:
        if is_linux or is_wsl or is_mac:
            new_stdout= ShellOut(sys.stdout, wrapped=True)
        elif is_windows:
            new_stdout = ShellOut(sys.stdout, wrapped=False)

    if new_stdout:
        sys.stdout = new_stdout
        sys.stderr = EWrapper(new_stdout, sys.stderr)
    
    return using_tk


def object_file_name(fpath: str) -> str:
    path = pathlib.Path(fpath)
    if path.suffix != ".c":
        logE("Not Compiling a C file")
        return None
    
    if is_windows:
        return path.with_suffix(".exe")
    else:
        return path.with_suffix(".o")


def simple_compile(fpath="test.c"):
    if not os.path.isfile(fpath):
        logE("Compiled file does not exist")
        return
    objfile = object_file_name(fpath)
    if not objfile:
        return

    t1 = time.perf_counter_ns()
    compile_proc = subprocess.run(
        ["gcc", "-o", objfile, fpath, "-lm"],
        capture_output=True)
    t2 = time.perf_counter_ns()
    if compile_proc.returncode != 0:
        logE(compile_proc.stderr.decode())
        return False
    
    timeMS = (t2 - t1) / 1e6
    logP(f"{fpath} compiled into an executable in {timeMS:.1f}ms!")
    return True


def shared_lib_file_name(fpath: str) -> str:
    path = pathlib.Path(fpath)
    if path.suffix != ".c":
        logE("Not Compiling a C file")
        return None
    
    if is_windows:
        return path.with_suffix(".dll")
    else:
        return path.with_suffix(".so")


def compile_shared(fpath="test.c"):
    # https://stackoverflow.com/questions/14884126/build-so-file-from-c-file-using-gcc-command-line

    if not os.path.isfile(fpath):
        logE("Compiled file does not exist")
        return
    sofile = shared_lib_file_name(fpath)
    if not sofile:
        return

    t1 = time.perf_counter_ns()
    compile_proc = subprocess.run(
        ["gcc", "-shared", "-o", sofile, "-fPIC", fpath],
        capture_output=True)
    t2 = time.perf_counter_ns()
    if compile_proc.returncode != 0:
        logE(compile_proc.stderr.decode())
        return False
    
    timeMS = (t2 - t1) / 1e6
    logP(f"{fpath} compiled into a shared library in {timeMS:.1f}ms!")
    return True


def load_shared(fpath="test"):
    path = pathlib.Path(fpath)

    if is_windows:
        path = path.with_suffix(".dll")
    else:
        path = path.with_suffix(".so")

    dbr = ctypes.CDLL(str(path.resolve()))
    a = ctypes.c_int(68)
    b = dbr.plus_one(a)
    print(b)
    return True


if __name__ == "__main__":

    using_tk = setup_stdio()

    sequential_checks(
        check_gcc_version,
        check_git_version,
        simple_compile,
        compile_shared,
        load_shared
    )

    if using_tk: 
        sys.stdout.window.mainloop()

        
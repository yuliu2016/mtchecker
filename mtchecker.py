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


def check_gcc_version():
    gcc_path = shutil.which("gcc");
    if not gcc_path:
        print("Error: GCC is not found. Did you install it?")
        return False
    print(f"Info: Found gcc at {gcc_path}")

    gccv = subprocess.run(["gcc", "--version"], capture_output=True)
    if gccv.returncode != 0:
        print("Error: GCC might be broken")
    
    v_line = gccv.stdout.decode().split("\n")[0].strip()
    print(f"Pass: <{v_line}>")

    version = v_line.split(" ")[-1]

    major, minor, _ = version.split(".")
    major, minor = int(major), int(minor)

    if major < 8 or (major == 8 and minor < 1):
        print("Warn: Your GCC version is older than the recommended version")
        return False
    return True


def check_git_version():
    git_path = shutil.which("git");
    if not git_path:
        print("Error: Git is not found. Did you install it?")
        return False
    print(f"Info: Found git at {git_path}")

    gitv = subprocess.run(["git", "--version"], capture_output=True)
    if gitv.returncode != 0:
        print("Error: git might be broken")
    
    v_line = gitv.stdout.decode().split("\n")[0].strip()
    print(f"Pass: <{v_line}>")
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
        self.window.geometry('600x600')

        win = self.window

        frm = Frame(win)

        options = [f"A{i}" for i in range(1,8)]
        svar = tkinter.StringVar(frm)
        svar.set("A1")
        self.selector = OptionMenu(frm, svar, *options)
        self.selector.pack(side=LEFT)

        self.btn2 = Button(frm, text="Open a new Folder")
        self.btn2.pack(side=LEFT)

        self.btn = Button(frm, text="Check my Code")
        self.btn.pack(side=LEFT)
        
        frm.pack()
        self.folder = Label(win, text=f"Project Folder: {os.getcwd()}")
        self.folder.pack()


        self.results = ScrolledText(self.window, width=80, height=80)
        self.results.pack()
        self.results.tag_config("t_blue", foreground="blue")
        self.results.tag_config("t_yellow", foreground="yellow")
        self.results.tag_config("t_red", foreground="red")
        self.results.tag_config("t_green", foreground="green")
    
    def flush():
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


def sequential_checks(*funcs: typing.Callable[..., bool]):
    for func in funcs:
        result = func()
        if not result:
            print(f"Error: Stopping at check <{func.__name__}>")
            break


def setup_stdout():
    using_tk = False
    if tk_lib_available:
        try:
            using_tk = True
            sys.stdout = TkOut()  # Use the graphical interface!!
        except TclError:
            pass
    
    if not using_tk:
        if is_linux or is_wsl or is_mac:
            sys.stdout = ShellOut(sys.stdout, wrapped=True)
        elif is_windows:
            sys.stdout = ShellOut(sys.stdout, wrapped=False)
    
    return using_tk


if __name__ == "__main__":

    using_tk = setup_stdout()

    sequential_checks(
        check_gcc_version,
        check_git_version
    )

    if using_tk: 
        sys.stdout.window.mainloop()

        
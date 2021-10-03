"""
MT2MP3 (student-made) code checker!
"""


import ctypes
import subprocess
import os
import sys
import re
import platform
import shutil
import tkinter
import argparse
import pathlib
import time
import math

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
    from tkinter.filedialog import askdirectory
    tk_lib_available = True
except ImportError:
    tk_lib_available = False
    ScrolledText, askdirectory = None, None


from typing import *


# Replaced with an actual interface later on
interface: Optional["PlainInterface"] = None


def logE(s):
    interface.logError(s)

def logI(s):
    interface.logInfo(s)

def logP(s):
    interface.logPass(s)

def logW(s):
    interface.logWarn(s)


class PlainInterface:
    def logError(self, s):
        print("Error: " + str(s), file=sys.stderr)

    def logInfo(self, s):
        print("Info: " + str(s))

    def logPass(self, s):
        print("Pass: " + str(s))

    def logWarn(self, s):
        print("Warn: " + str(s))


class ColoredInterface:
    def logError(self, s):
        print("\033[31m" + str(s) + "\033[0m")

    def logInfo(self, s):
        print("\033[34m" + str(s) + "\033[0m")

    def logPass(self, s):
        print("\033[35m" + str(s) + "\033[0m")

    def logWarn(self, s):
        print("\033[33m" + str(s) + "\033[0m")


def check_gcc_version():
    gcc_path = shutil.which("gcc")
    if not gcc_path:
        logE("GCC is not found. Did you install it?")
        return False
    logI(f"Found gcc at {gcc_path}")

    gccv = subprocess.run(["gcc", "--version"], 
        capture_output=True, stdin=subprocess.DEVNULL)

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
    git_path = shutil.which("git")
    if not git_path:
        logE("Git is not found. Did you install it?")
        return False
    logI(f"Found git at {git_path}")

    gitv = subprocess.run(["git", "--version"], 
        capture_output=True, stdin=subprocess.DEVNULL)

    if gitv.returncode != 0:
        logE("git might be broken")
    
    v_line = gitv.stdout.decode().split("\n")[0].strip()
    logI(f"<{v_line}>")
    return True


def object_file_name(fpath: str):
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


def shared_lib_file_name(fpath: str):
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


def parse_signature(sig: str):
    if not re.match("\(()*\)", sig):
        return None


class FunctionRunner:
    def __init__(self, file_path, func_signature, kwargs) -> None:
        self.file_path = file_path
        self.func_signature = func_signature
        self.kwargs = kwargs
        self.name = ""
        self.steps = []

    def add_test_step(self, step_options):
        self.steps.append(step_options)


class GCCRunner(FunctionRunner):
    def __init__(self, file_path, func_signature, kwargs) -> None:
        super().__init__(file_path, func_signature, kwargs)


class TestFunction:
    def __init__(self, runner) -> None:
        self.__runner = runner

    def __enter__(self) :
        return self

    def __exit__(self, *exc_info):
        pass

    def test(self, **kwargs):
        self.__runner.add_test_step(kwargs)

    def note(self, msg):
        self.test(msg=msg)


CHECKLIST: "List[TestSuite]" = []

class TestSuite:
    def __init__(self, name: str, path_format: str, add_to_checklist=True) -> None:
        self.name = name
        self.path_format = path_format
        self.funcs: List[FunctionRunner] = []

        if add_to_checklist:
            CHECKLIST.append(self)

    def func(self,
        file_arg: Union[int, str], 
        func_signature: str, 
        runner: Type[FunctionRunner]=GCCRunner, 
        **kwargs):

        file_path = self.path_format.format(file_arg)

        runner_inst = runner(file_path, func_signature, kwargs)
        func = TestFunction(runner_inst)
        self.funcs.append(runner_inst)
        return func


class ChecklistExecutor:
    def __init__(self, config: "InitConfig", checklist: List[TestSuite]) -> None:
        self.config = config
        self.checklist = checklist

    def run_tests(self, path: str, suite_no: Optional[int], tests: Optional[List[int]]):
        if not os.path.isabs(path):
            logE("Test path not absolute")
            return
        
        tmp = os.path.join(path, "tmp/")

        if not suite_no:
            suite_no = len(self.checklist) - 1
        suite = self.checklist[suite_no]

        if not tests:
            tests = range(len(suite.funcs))
        

    def run_configured(self):
        self.run_tests(self.config.path, self.config.suite_no, self.config.tests)


    def query_suites(self):
        suites = self.checklist
        names = []
        for suite in suites:
            names.append(suite.name)
        return names

    def query_funcs(self, index):
        suite = self.checklist[index]
        names = []
        for func in suite.funcs:
            names.append(func.name)
        return names


class TkInterface:
    def __init__(self, executor: ChecklistExecutor) -> None:
        self.executor = executor

        self.window = Tk()
        self.window.title("2MP3 Code Checker")

        win = self.window

        frm = Frame(win)

        options = executor.query_suites()
        svar = tkinter.StringVar(frm)
        svar.set("Assignment 1")
        self.selector = OptionMenu(frm, svar, *options)
        self.selector.pack(side=LEFT)

        options2 = ["All Questions"] + [f"Question {i}" for i in range(1,8)]
        svar2 = tkinter.StringVar(frm)
        svar2.set("All Questions")
        self.selector2 = OptionMenu(frm, svar2, *options2)
        self.selector2.pack(side=LEFT)

        self.btn2 = Button(frm, text="Open Folder", command=self.open_folder)
        self.btn2.pack(side=LEFT)

        self.btn = Button(frm, text="Run Code Checker", command=self.check_code)
        self.btn.pack(side=LEFT)
        
        frm.pack()
        self.dir = executor.config.path
        self.foldervar = StringVar()
        self.update_dir_label()
        self.folder = Label(win, textvariable=self.foldervar)
        self.folder.pack()


        self.results = ScrolledText(self.window, width=80, height=24, selectbackground="lightgray")
        self.results.pack()

        self.results.tag_config("t_blue", foreground="blue")
        self.results.tag_config("t_yellow", foreground="yellow")
        self.results.tag_config("t_red", foreground="red")
        self.results.tag_config("t_green", foreground="green")


    def run_blocking(self):
        mainloop()

    
    def update_dir_label(self):
        self.foldervar.set(f"Project Folder: {self.dir}")

    def open_folder(self):
        self.dir = askdirectory()
        if dir:
            self.update_dir_label()
            logI(f"Opened project folder {self.dir}")

    def check_code(self):
        logI("Checked the code!")


    def __log(self, s, c):
        self.results.insert(END, str(s)+"\n", c)

    
    def logInfo(self, s):
        self.__log(s, "t_blue")

    def logWarn(self, s):
        self.__log(s, "t_yellow")

    def logError(self, s):
        self.__log(s, "t_red")

    def logPass(self, s):
        self.__log(s, "t_green")


class InitConfig(NamedTuple):
    path: str
    display: str
    suite_no: Optional[int]
    tests: Optional[List[int]]


def init_config():
    parser = argparse.ArgumentParser()

    parser.add_argument("-p", 
        help="specify the root project directory, pwd if unset", metavar="PATH")

    parser.add_argument("-s", metavar="SUITE", type=int,
        help="specify the test suite number. Last suite tested if unset.")
    parser.add_argument("-t", metavar="TEST", type=int, nargs="+",
        help="specify the test numbers. All from each suite are tested if unset")

    parser.add_argument("-d", 
        help="specify the mode of display",
        choices=["any", "plain", "colored", "graphical"],
        default="any")

    args = parser.parse_args()

    if args.p:
        definite_path = args.p
    else:
        definite_path = os.getcwd()

    return InitConfig(definite_path, args.d, args.s, args.t)



def run_checker():
    config = init_config()
    executor = ChecklistExecutor(config, CHECKLIST)

    global interface

    display = config.display
    if display not in ["plain", "colored", "graphical"]:
        if tk_lib_available:
            display = "graphical"
        else:
            if is_linux or is_wsl or is_mac:
                display = "colored"
            else:
                display = "plain"

    if display == "graphical" and tk_lib_available:
        try:
            interface = TkInterface(executor)
        except TclError:
            interface = PlainInterface()
        else:
            interface.run_blocking()

    elif display == "colored":
        interface = ColoredInterface()
        executor.run_configured()
    else:
        interface = PlainInterface()
        executor.run_configured()



DEFAULT_PATH_FORMAT = os.path.join("A1", "Q{0}","question{0}.c")

A1 = TestSuite(
    name="Assignment 1",
    path_format=DEFAULT_PATH_FORMAT
)

with A1.func(1, "int minutes (int m, int h, int d)") as f:
    f.test(args=(1,1,1), expect=1501)
    f.test(args=(30,15,2), expect=3810)
    f.test(args=(0,0,0), expect=0)
    

with A1.func(2, "float onethird (int n)") as f:
    f.test(args=(1,), expect=1.000000, threshold=1e-6)
    f.test(args=(10,), expect=0.385000, threshold=1e-6)
    f.test(args=(9999,), expect=0.333383, threshold=1e-6)
    
with A1.func(3, "int multiples (int x, int y, int N)") as f:
    f.test(args=(2,3,10), expect=42) # given case
    f.test(args=(4,10,20), expect=70)
    f.test(args=(32,14,10), expect=0)
    f.test(args=(11,15,20), expect=26)

with A1.func(4, "float compoundInterest (float p, int a, int n)") as f:
    f.test(args=(0.05,20,5), expect=25.53, threshold=1e-3)
    f.test(args=(0.10,910,3), expect=1211.21, threshold=1e-3)
    f.test(args=(0.06,800,2), expect=898.88, threshold=1e-3)

with A1.func(5, "int LeapYearCheck (int n)") as f:
    f.test(args=(2000,), expect=1)
    f.test(args=(2021,), expect=0)
    f.test(args=(1752,), expect=1)
    f.test(args=(2100,), expect=0)

with A1.func(6, "int FactorialWhile (int n)") as f:
    f.test(args=(3,), expect=6)
    f.test(args=(0,), expect=1)
    f.test(args=(10,), expect=3628800)

with A1.func(6, "int FactorialDoWhile (int n)") as f:
    f.test(args=(3,), expect=6)
    f.test(args=(0,), expect=1)
    f.test(args=(10,), expect=3628800)

with A1.func(7, "void mileage (void)") as f:
    f.note("Not currently tested")



if __name__ == "__main__":
    run_checker()

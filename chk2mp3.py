"""
MT2MP3 (student-made) code checker!
"""


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
import threading

plat = platform.system()
is_windows = plat == "Windows"
is_mac = plat == "Darwin"
is_linux = plat == "Linux"

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

def logA(s):
    interface.logAccent(s)

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
        self.logInfo(s)

    def logAccent(self, s):
        self.logInfo(s)

    def logWarn(self, s):
        print("Warn: " + str(s))


class ColoredInterface:
    def logError(self, s):
        print("\033[31m" + str(s) + "\033[0m")

    def logInfo(self, s):
        print("\033[34m" + str(s) + "\033[0m")

    def logPass(self, s):
        print("\033[32m" + str(s) + "\033[0m")

    def logAccent(self, s):
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


def center_text(s: str, w: int):
    L = len(s)
    if L > w: return s
    return " " * ((w - L) // 2) + s

class CSignature(NamedTuple):
    ret_type: str
    name: str
    arg_types: List[str]


def parse_c_signature(sig: str):
    # todo add a proper parser here
    L, R = sig.split("(")
    L = L.strip().split(" ")
    R = R.strip().strip(")")
    name = L[-1]
    ret = " ".join(L[:-1])
    A = R.split(",")
    args = []
    for arg_def in A:
        sp = arg_def.split(" ")
        args.append(" ".join(sp[:-1]))
    return CSignature(ret, name, args)


class TestResult(NamedTuple):
    pass

class FunctionRunner:
    def __init__(self, file_subpath, func_signature, args, kwargs):
        self.file_subpath = file_subpath
        self.func_signature = func_signature
        self.args = args
        self.kwargs = kwargs
        self.name = ""
        self.steps = []
        self.tmp_path: Optional[pathlib.Path] = None
        self.abs_path = None

    def add_test_step(self, step_options):
        self.steps.append(step_options)

    def configure_path(self, root, tmp):
        self.abs_path = os.path.join(root, self.file_subpath)
        self.tmp_path = pathlib.Path(tmp)

    def exec_simple(self):
        pass


class GCCRunner(FunctionRunner):
    def __init__(self, file_subpath, func_signature, args, kwargs):
        super().__init__(file_subpath, func_signature, args, kwargs)
        self.signature = parse_c_signature(func_signature)
        self.name = self.signature.name

    def object_file_name(self, fpath: str):
        path = pathlib.Path(fpath)
        if path.suffix != ".c":
            logE("Not Compiling a C file")
            return None

        if is_windows:
            return path.with_suffix(".exe")
        else:
            return path.with_suffix(".o")

    def exec_simple(self):
        source_path = pathlib.Path(self.abs_path)
        if source_path.suffix != ".c":
            logE("Not Compiling a C file; Incompatible runner")
            return
        if not source_path.exists():
            logE("File to be compiled does not exist")
            return

        logA(f"Checking '{self.func_signature}' in '{source_path.name}'")

        stem = source_path.stem
        objfile = self.tmp_path / stem

        flags = ["-Wall"]
        if self.args:
            flags.append(self.args)

        command = ["gcc", *flags, "-o", str(objfile), str(source_path)]

        t1 = time.perf_counter_ns()
        compile_proc = subprocess.run(command, capture_output=True, stdin=subprocess.DEVNULL)
        t2 = time.perf_counter_ns()
        timeMS = (t2 - t1) / 1e6

        if compile_proc.returncode != 0:
            logE(compile_proc.stderr.decode())
            return False

        flags_join = " ".join(flags)
        logP(f"  [GCC] Compiled in {timeMS:.1f}ms with flags '{flags_join}'")
        return True


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
    def __init__(self, name: str, path_format: str, add_to_checklist=True):
        self.name = name
        self.path_format = path_format
        self.funcs: List[FunctionRunner] = []

        if add_to_checklist:
            CHECKLIST.append(self)

    def func(self,
        file_arg: Union[int, str], 
        func_signature: str,
        args: str = "",
        runner: Type[FunctionRunner]=GCCRunner, 
        **kwargs):

        file_path = self.path_format.format(file_arg)

        runner_inst = runner(file_path, func_signature, args, kwargs)
        func = TestFunction(runner_inst)
        self.funcs.append(runner_inst)
        return func


class ChecklistExecutor:
    def __init__(self, config: "InitConfig", checklist: List[TestSuite]):
        self.config = config
        self.checklist = checklist
        self.prelim_checked = False
        self.prev_path = None

    def check_paths(self, path: str):
        if not os.path.isabs(path):
            logE("Test path not absolute")
            return None

        tmp = os.path.join(path, ".chk2mp3/")
        if os.path.isdir(tmp):
            shutil.rmtree(tmp)
        os.mkdir(tmp)
        return tmp

    def run_prelim_checks(self, path):
        if self.prelim_checked and path == self.prev_path:
            return True
        self.prev_path = None

        if not check_gcc_version() or not check_git_version():
            return False
        self.prelim_checked = True
        self.prev_path = path
        return True

    def run_tests(self, path: str, suite_no: Optional[int], tests: Optional[List[int]]):
        tmp = self.check_paths(path)
        if not tmp:
            return

        if not self.run_prelim_checks(path):
            return

        if suite_no:
            if 0 <= suite_no < len(self.checklist):
                suite = self.checklist[suite_no]
            else:
                logE(f"Invalid suite number to run: {suite_no}")
                return
        else:
            suite = self.checklist[-1]

        if not tests:
            tests = range(len(suite.funcs))

        total_steps = 0
        for test_no in tests:
            if not (0 <= test_no < len(suite.funcs)):
                logE(f"Invalid test number {test_no}. Aborting...")
                return
            total_steps += len(suite.funcs[test_no].steps)

        logI("=" * 80)
        title = f"{suite.name} (Total: {len(tests)} Functions, {total_steps} Test Steps)"
        logI(center_text(title, 80))
        logI("=" * 80)

        for test_no in tests:
            runner = suite.funcs[test_no]
            runner.configure_path(path, tmp)
            runner.exec_simple()
            logI("")
        

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


class ThreadSafeItemStore:
    # https://stackoverflow.com/questions/16745507/tkinter-how-to-use-threads-to-preventing-main-event-loop-from-freezing
    # https://stackoverflow.com/questions/156360/get-all-items-from-thread-queue

    def __init__(self):
        self.cond = threading.Condition()
        self.items = []

    def add(self, item):
        with self.cond:
            self.items.append(item)
            self.cond.notify()  # Wake 1 thread waiting on cond (if any)

    def getAll(self, blocking=False):
        with self.cond:
            # If blocking is true, always return at least 1 item
            while blocking and len(self.items) == 0:
                self.cond.wait()
            items, self.items = self.items, []
        return items

    def clear(self):
        self.items = []


class TkInterface:
    def __init__(self, executor: ChecklistExecutor):
        self.executor = executor

        self.window = Tk()
        self.window.title("2MP3 Code Checker")

        win = self.window
        win.resizable(False, False)

        frm = Frame(win)

        options = executor.query_suites()
        svar = tkinter.StringVar(frm)
        svar.set("Assignment 1")
        self.selector = OptionMenu(frm, svar, *options)
        self.selector.pack(side=LEFT)

        options2 =["All Functions"] + executor.query_funcs(0) # + [f"Question {i}" for i in range(1,8)]
        svar2 = tkinter.StringVar(frm)
        svar2.set("All Functions")
        self.selector2 = OptionMenu(frm, svar2, *options2)
        self.selector2.pack(side=LEFT)

        btn2 = Button(frm, text="Open Folder", command=self.open_folder)
        btn2.pack(side=LEFT)

        btn = Button(frm, text="Run Code Checker", command=self.check_code)
        btn.pack(side=LEFT)

        btn3 = Button(frm, text="Clear Window", command=self.clear_log)
        btn3.pack(side=LEFT)

        frm.pack()
        self.dir = executor.config.path
        self.foldervar = StringVar()
        self.update_dir_label()
        self.folder = Label(win, textvariable=self.foldervar)
        self.folder.pack()


        self.log = ScrolledText(self.window, width=80, height=32,
                                selectbackground="lightgray", state=DISABLED)
        self.init_log()

        # Threading Objects
        self.log_queue = ThreadSafeItemStore()
        self.thread: Optional[threading.Thread] = None


    def init_log(self):
        self.log.pack()

        self.log.tag_config("t_blue", foreground="blue")
        self.log.tag_config("t_orange", foreground="orange")
        self.log.tag_config("t_red", foreground="red")
        self.log.tag_config("t_green", foreground="darkgreen")
        self.log.tag_config("t_magenta", foreground="magenta")

    def run_blocking(self):
        self.window.mainloop()

    def update_dir_label(self):
        self.foldervar.set(f"Project Folder: {self.dir}")

    def open_folder(self):
        self.dir = askdirectory()
        if dir:
            self.update_dir_label()
            logI(f"Opened project folder {self.dir}")

    def check_code(self):
        if self.thread is not None:
            logW("There is still a process running! Wait until it finishes")
            return
        self.log_queue.clear()
        self.thread = threading.Thread(target=self.check_code_new_thread)
        self.thread.start()
        self.window.after(100, self.process_log_queue)

    def check_code_new_thread(self):
        self.executor.run_configured()
        # todo self.executor.run_tests()
        self.thread = None

    def clear_log(self):
        self.log.configure(state=NORMAL)
        self.log.delete("1.0", END)
        self.log.configure(state=DISABLED)

    def process_log_queue(self):
        # Runs on tk thread
        to_be_processed = self.log_queue.getAll(blocking=False)

        if to_be_processed:
            self.log.configure(state=NORMAL)
            for s, c in to_be_processed:
                self.log.insert(END, s, c)
            self.log.configure(state=DISABLED)

        if self.thread:
            self.window.after(100, self.process_log_queue)

    def __unsafe_log(self, s, c):
        self.log_queue.add((str(s) + "\n", c))

    def logInfo(self, s):
        self.__unsafe_log(s, "t_blue")

    def logWarn(self, s):
        self.__unsafe_log(s, "t_orange")

    def logError(self, s):
        self.__unsafe_log(s, "t_red")

    def logPass(self, s):
        self.__unsafe_log(s, "t_green")

    def logAccent(self, s):
        self.__unsafe_log(s, "t_magenta")


class InitConfig(NamedTuple):
    path: str  # Must be the absolute path
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
        definite_path = os.path.abspath(args.p)
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
    

with A1.func(2, "float onethird (int n)", "-lm") as f:
    f.test(args=(1,), expect=1.000000, threshold=1e-6)
    f.test(args=(10,), expect=0.385000, threshold=1e-6)
    f.test(args=(9999,), expect=0.333383, threshold=1e-6)
    
with A1.func(3, "int multiples (int x, int y, int N)") as f:
    f.test(args=(2,3,10), expect=42) # given case
    f.test(args=(4,10,20), expect=70)
    f.test(args=(32,14,10), expect=0)
    f.test(args=(11,15,20), expect=26)

with A1.func(4, "float compoundInterest (float p, int a, int n)", "-lm") as f:
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

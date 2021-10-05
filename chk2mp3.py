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
import signal

from typing import *

try:
    from tkinter import *
    from tkinter.scrolledtext import ScrolledText
    from tkinter.filedialog import askdirectory
    tk_lib_available = True
except ImportError:
    tk_lib_available = False
    ScrolledText, askdirectory = None, None


plat = platform.system()
is_windows = plat == "Windows"
is_mac = plat == "Darwin"
is_linux = plat == "Linux"

# https://www.scivision.dev/python-detect-wsl/
is_wsl = is_linux and "Microsoft" in platform.uname()

if is_windows:
    EXECUTABLE_EXT = ".exe"
    SHAREDLIB_EXT = ".dll"
else:
    EXECUTABLE_EXT = ""
    SHAREDLIB_EXT = ".so"


# Replaced with an actual interface later on
interface: Optional["PlainInterface"] = None
CONSOLE_WIDTH = 80

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
        print(str(s), file=sys.stderr)

    def logInfo(self, s):
        print(str(s))

    def logPass(self, s):
        self.logInfo(s)

    def logAccent(self, s):
        self.logInfo(s)

    def logWarn(self, s):
        self.logInfo(s)


class ColoredInterface:

    def _print(self, s, c):
        if not s: print()
        else: print(c + str(s) + "\033[0m")

    def logError(self, s):
        self._print(s, "\033[31m")

    def logInfo(self, s):
        self._print(s, "\033[36m")

    def logPass(self, s):
        self._print(s, "\033[32m")

    def logAccent(self, s):
        self._print(s, "\033[35m")

    def logWarn(self, s):
        self._print(s, "\033[33m")


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

def indent_text(s:str, i):
    return "\n".join(" "*i + x for x in s.splitlines())

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

class TestTransform:
    pass

class CTestTransform:
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
        self.next_transform: Optional[TestTransform] = None

    def add_test_step(self, step_args):
        # Filter out empty/stub tests
        if step_args:
            if self.next_transform:
                t = self.next_transform
            else:
                t = None
            self.steps.append((t, step_args))


    def set_test_transform(self, transform, fmt, kwargs):
        self.next_transform = transform(fmt, kwargs)

    def configure_path(self, root, tmp):
        self.abs_path = os.path.join(root, self.file_subpath)
        self.tmp_path = pathlib.Path(tmp)
        return True

    def exec_simple(self):
        pass


class GCCRunner(FunctionRunner):
    def __init__(self, file_subpath, func_signature, args, kwargs):
        super().__init__(file_subpath, func_signature, args, kwargs)
        self.signature = parse_c_signature(func_signature)
        self.name = self.signature.name
        self.source_path: Optional[pathlib.Path] = None

    def object_file_name(self, fpath: str):
        path = pathlib.Path(fpath)
        if path.suffix != ".c":
            logE("Not Compiling a C file")
            return None

        if is_windows:
            return path.with_suffix(".exe")
        else:
            return path.with_suffix(".o")

    def configure_path(self, root, tmp):
        super().configure_path(root, tmp)

        source_path = pathlib.Path(self.abs_path)
        if source_path.suffix != ".c":
            logE("Not Compiling a C file; Incompatible runner")
            return False
        if not source_path.exists():
            logE("File to be compiled does not exist")
            return False

        logA(f"Checking '{self.func_signature}' in '{source_path.name}'")
        self.source_path = source_path
        return True


    def compile_object(self):
        source_path = self.source_path

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

        err_out = compile_proc.stderr.decode()

        if compile_proc.returncode != 0:
            logE(indent_text(err_out, 2))
            return False

        if err_out:
            logW(indent_text(err_out.strip(), 2))

        flags_join = " ".join(flags)
        logP(f"  [GCC] Compiled in {timeMS:.1f}ms with flags '{flags_join}'")
        return True

    def compile_shared(self):
        source_path = self.source_path

        stem = source_path.stem
        sofile = (self.tmp_path / stem).with_suffix(SHAREDLIB_EXT)

        command = ["gcc", "-shared", "-o", str(sofile), "-fPIC", str(source_path)]

        compile_proc = subprocess.run(command, capture_output=True, stdin=subprocess.DEVNULL)

        if compile_proc.returncode != 0:
            err_out = compile_proc.stderr.decode()
            logE(indent_text(err_out, 2))
            return False

        logI("  [GCC] Recompiled function into a shared library")
        return True


    def exec_simple(self):
        if not self.compile_object():
            return
        if not self.compile_shared():
            return


class TestFunction:
    def __init__(self, runner) -> None:
        self.__runner = runner


    def __enter__(self) :
        return self

    def __exit__(self, *exc_info):
        pass

    def set_format(self, fmt, transform: Type[TestTransform]=CTestTransform, **kwargs):
        self.__runner.set_test_transform(transform, fmt, kwargs)

    def test(self, **kwargs):
        self.__runner.add_test_step(kwargs)


CHECKLIST: "List[TestSuite]" = []

class TestSuite:
    def __init__(self, name: str, path_format: str, add_to_global_checklist=True):
        self.name = name
        self.path_format = path_format
        self.funcs: List[FunctionRunner] = []

        if add_to_global_checklist:
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

    # noinspection PyTypeChecker
    def __init__(self, config: "InitConfig", checklist: List[TestSuite]):
        self.config = config
        self.checklist = checklist

        self.prelim_checked = False
        self.prev_path = None

        # Variables only set during test execution

        self._path: str = ""
        self._tmp_dir: str = ""
        self._suite: TestSuite = None
        self._total_steps = 0
        self._tests: List[int] = []

    def create_tmp_dir(self, path: str):
        if not os.path.isabs(path):
            logE("Test path not absolute")
            return False

        tmp = os.path.join(path, ".chk2mp3/")
        if os.path.isdir(tmp):
            shutil.rmtree(tmp)
        os.mkdir(tmp)

        self._tmp_dir = tmp
        self._path = path
        return True

    def check_installs_once(self, path):
        if self.prelim_checked and path == self.prev_path:
            return True
        self.prev_path = None

        if not check_gcc_version() or not check_git_version():
            return False
        self.prelim_checked = True
        self.prev_path = path
        return True

    def check_suite_and_tests(self, suite_no: Optional[int], tests: Optional[List[int]]):
        if suite_no:
            if 0 <= suite_no < len(self.checklist):
                self._suite = self.checklist[suite_no]
            else:
                logE(f"Invalid suite number to run: {suite_no}")
                return False
        else:
            self._suite = self.checklist[-1]

        if not tests:
            tests = range(len(self._suite.funcs))

        self._total_steps = 0

        for test_no in tests:
            if not (0 <= test_no < len(self._suite.funcs)):
                logE(f"Invalid test number {test_no}. Aborting...")
                return False
            self._total_steps += len(self._suite.funcs[test_no].steps)

        self._tests = tests

        return True

    def _checked_run(self):
        self.print_title()

        for test_no in self._tests:
            runner = self._suite.funcs[test_no]
            if runner.configure_path(self._path, self._tmp_dir):
                runner.exec_simple()
                logI("")

    def print_title(self):
        logI("=" * CONSOLE_WIDTH)
        title = f"{self._suite.name} (Total: " \
                f"{len(self._tests)} Functions, {self._total_steps} Test Steps)"
        logI(center_text(title, CONSOLE_WIDTH))
        logI("=" * CONSOLE_WIDTH)

    def cleanup(self):
        if not self.config.debug:
            shutil.rmtree(self._tmp_dir)
        logP("Cleaned up temporary directory")

    def run_tests(self, path: str, suite_no: Optional[int], tests: Optional[List[int]]):
        if not self.check_suite_and_tests(suite_no, tests): return
        if not self.check_installs_once(path): return
        if not self.create_tmp_dir(path): return

        try:
            self._checked_run()
        finally:
            self.cleanup()

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
        global CONSOLE_WIDTH
        CONSOLE_WIDTH = 88

        self.executor = executor

        self.window = Tk()
        self.window.title("2MP3 Code Checker")

        win = self.window
        win.resizable(False, False)

        top_frame = Frame(win)

        options = executor.query_suites()
        svar = tkinter.StringVar(top_frame)
        svar.set(options[-1])
        self.selector = OptionMenu(top_frame, svar, *options)
        self.selector.pack(side=LEFT)

        options2 =["All Functions"] + executor.query_funcs(-1)
        svar2 = tkinter.StringVar(top_frame)
        svar2.set("All Functions")
        self.selector2 = OptionMenu(top_frame, svar2, *options2)
        self.selector2.pack(side=LEFT)

        self.init_buttons(top_frame)

        top_frame.pack()
        self.dir = executor.config.path
        self.foldervar = StringVar()
        self.update_dir_label()
        self.folder = Label(win, textvariable=self.foldervar)
        self.folder.pack()


        self.log = ScrolledText(self.window, width=88, height=32,
                                selectbackground="lightgray", state=DISABLED)
        self.init_log()

        # Threading Objects
        self.log_queue = ThreadSafeItemStore()
        self.thread: Optional[threading.Thread] = None

    def init_buttons(self, frame):
        btn2 = Button(frame, text="Open Folder", command=self.open_folder)
        btn2.pack(side=LEFT)

        btn = Button(frame, text="Run Code Checker", command=self.check_code)
        btn.pack(side=LEFT)

        btn3 = Button(frame, text="Clear Window", command=self.clear_log)
        btn3.pack(side=LEFT)

    def init_log(self):
        self.log.pack()

        self.log.tag_config("t_blue", foreground="blue")
        self.log.tag_config("t_orange", foreground="#ff6000")
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
    display_mode: str
    suite_no: Optional[int]
    tests: Optional[List[int]]
    debug: bool


def init_config():
    parser = argparse.ArgumentParser()

    parser.add_argument("-p", 
        help="specify the root project directory, pwd if unset", metavar="PATH")

    parser.add_argument("-s", metavar="SUITE", type=int,
        help="specify the test suite (i.e. assignment) number. Last suite tested if unset.")
    parser.add_argument("-t", metavar="TEST", type=int, nargs="+",
        help="specify the test numbers. All from each suite are tested if unset")

    parser.add_argument("-m",
        help="specify the mode of presentation",
        choices=["any", "plain", "colored", "graphical"],
        default="any")

    parser.add_argument("-d",
        help="turn on debug mode (keeps temp folder)",
        action="store_true")

    args = parser.parse_args()

    if args.p:
        definite_path = os.path.abspath(args.p)
    else:
        definite_path = os.getcwd()

    return InitConfig(definite_path, args.m, args.s, args.t, args.d)



def run_checker():
    config = init_config()
    executor = ChecklistExecutor(config, CHECKLIST)

    global interface

    display = config.display_mode
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



A1 = TestSuite(
    name="Assignment 1",
    path_format=os.path.join("A1", "Q{0}","question{0}.c")
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
    f.test()


A2 = TestSuite(
    name="Assignment 2",
    path_format=os.path.join("A2", "Q{0}","question{0}.c")
)


with A2.func(1, "double mean(int* x, int size)", "-lm") as f:
    f.set_format("ai:x[]={$a};~lf:r=$n(x,$ac)", cond="abs(r-$e)<$t")
    f.test(args=[1,2,3,4,5], expect=3.0, thres=1e-6)

with A2.func(1, "double median(int* x, int size)") as f:
    f.set_format("ai:x[]={$a};~lf:r=$n(x,$ac)", cond="abs(r-$e)<$t")
    f.test()

with A2.func(1, "int mode(int* x, int size)") as f:
    f.set_format("ai:x[]={$a};~i:r=$n(x,$ac)", cond="r==$e")
    f.test()

with A2.func(2, "int juggler(int n)") as f:
    f.set_format("~i:r=$n($a)", cond="r==$e")
    f.test(args=(20,), expect=3)
    f.test(args=(10000,), expect=9)
    f.test(args=(10001, ), expected_code=signal.SIGSEGV)

with A2.func(3, "int bubblesort(int* x, int size)") as f:
    f.set_format("ai:x[]={$a},ai:e[]={$e2},~i:r=$n(x,$ac);~ai:x",
                 cond="r==$e1&&!(memcmp(x,e,$ac*sizeof(int)))", incl="memory.h")
    f.test(args=[548, 845, 731, 258, 809, 522, 73, 385, 906, 891, 988, 289, 808, 128],
           expect=(47, [73, 128, 258, 289, 385, 522, 548, 731, 808, 809, 845, 891, 906, 988]))
    f.test(args=[100], expect=(0,[100]))

with A2.func(4, "int insertionsort(int* x, int size)") as f:
    f.set_format("ai:x[]={$a},ai:e[]={$e2},~i:r=$n(x,$ac);~ai:x",
                 cond="r==$e1&&!(memcmp(x,e,$ac*sizeof(int)))", incl="memory.h")
    f.test(args=[548, 845, 731, 258, 809, 522, 73, 385, 906, 891, 988, 289, 808, 128],
           expect=(47, [73, 128, 258, 289, 385, 522, 548, 731, 808, 809, 845, 891, 906, 988]))
    f.test(args=[100], expect=(0,[100]))


with A2.func(5, "int binsearch(int* x, int y, int size)") as f:
    f.set_format("ai:x[]={$a1};i:y=$a2;~i:r=$n(x,y,$a1c)", cond="r==$e")

    f.test(args=([22, 25, 37, 42, 56, 56, 60, 69, 73, 75, 94, 109, 129, 132, 134, 148, 160, 168, 168, 169, 172,
177, 235, 238, 240, 263, 272, 274, 291, 303, 305, 309, 310, 311, 312, 317, 327, 332, 336, 341, 347,
358, 359, 373, 387, 389, 392, 404, 425, 428, 431, 438, 444, 481, 490, 491, 496, 503, 506, 511, 521,
554, 554, 555, 559, 565, 572, 580, 587, 587, 617, 642, 643, 660, 681, 684, 697, 712, 726, 726, 739,
757, 761, 775, 790, 826, 828, 832, 853, 865, 886, 886, 888, 901, 918, 937, 945, 952, 971, 974], 506), expect=5)

    f.test(args=([22, 25, 37, 42, 56, 56, 60, 69, 73, 75, 94, 109, 129, 132, 134, 148, 160, 168, 168, 169, 172,
177, 235, 238, 240, 263, 272, 274, 291, 303, 305, 309, 310, 311, 312, 317, 327, 332, 336, 341, 347,
358, 359, 373, 387, 389, 392, 404, 425, 428, 431, 438, 444, 481, 490, 491, 496, 503, 506, 511, 521,
554, 554, 555, 559, 565, 572, 580, 587, 587, 617, 642, 643, 660, 681, 684, 697, 712, 726, 726, 739,
757, 761, 775, 790, 826, 828, 832, 853, 865, 886, 886, 888, 901, 918, 937, 945, 952, 971, 974],300), expect=-1)

    f.test(args=([100], 100), expect=1)


if __name__ == "__main__":
    run_checker()

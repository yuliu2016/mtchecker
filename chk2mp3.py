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


class TextInterface:

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

# Replaced with an actual interface later on
interface = TextInterface()
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


class ColoredInterface(TextInterface):

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

def replace(s, to_replace):
    for k, v in reversed(to_replace.items()):
        s = s.replace("$" + k, str(v))
    return s


class CSignature(NamedTuple):
    ret_type: str
    name: str
    arg_types: List[str]



class TestRunner:
    def __init__(self, root, tpath, tmp, suite, test, steps):
        self.root = root
        self.test_path = tpath
        self.tmp_path = pathlib.Path(tmp)
        self.suite = suite
        self.test = test
        self.steps = steps
        self.abs_path = None

    def exec_simple(self):
        pass


class GCCRunner(TestRunner):
    def __init__(self, root, tpath, tmp, suite, test, steps):
        super().__init__(root, tpath, tmp, suite, test, steps)
        self.source_path_root = pathlib.Path(root) / suite / test
        self.test_path_root = pathlib.Path(tpath) / suite / test
        self.compiled_files = []


    def object_file_name(self, fpath: str):
        path = pathlib.Path(fpath)
        if path.suffix != ".c":
            logE("Not Compiling a C file")
            return None

        if is_windows:
            return path.with_suffix(".exe")
        else:
            return path.with_suffix(".o")


    def compile_object(self, source_path, flags=("-Wall", "-lm"), post_flags=tuple(), disp_name="source"):

        stem = source_path.stem
        objfile = self.tmp_path / stem

        command = ["gcc", *flags, "-o", str(objfile), str(source_path), *post_flags]

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
        logP(f"  [GCC] Compiled {disp_name} in {timeMS:.1f}ms with flags '{flags_join}'")
        return True

    def compile_shared(self, source_path):
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

    def resolve_step_file(self, step: str):
        try:
            a, b = step.split("_")
            c, e = b.split(".")
            if e != "c" or not c.startswith("test"): raise ValueError

            return a + ".c", int(c[4:])
        except ValueError:
            return None, None

    def exec_step(self, step: str):
        fname, step_no = self.resolve_step_file(step)
        if not fname:
            logE(f"Cannot resolve file for {step}")
            return

        source_path = self.source_path_root / fname
        if not source_path.exists():
            logE("File to be compiled does not exist")
            return

        logA(f"Checking step {step_no} in '{source_path.name}'")
        if fname in self.compiled_files:
            logI("  File has already been compiled")
        else:
            if not self.compile_object(source_path):return
            if not self.compile_shared(source_path):return
            self.compiled_files.append(fname)

        sofile = (self.tmp_path / fname).with_suffix(SHAREDLIB_EXT)
        step_path = self.test_path_root / step

        if not self.compile_object(step_path,
            post_flags=(str(sofile),), disp_name=f"'{step}'"): return


    def exec_simple(self):
        for step in self.steps:
            self.exec_step(step)
            logI("")

class ProbingExecutor:

    # noinspection PyTypeChecker
    def __init__(self, config: "InitConfig", runners: Dict[Any,Type[TestRunner]]):
        self.config = config
        self.runners = runners

        self.ready = False
        self.suites: Dict[str,Dict[str,List[str]]] = {}

        self.prelim_checked = False
        self.prev_path = None

        # Variables only set during test execution

        self._path: str = ""
        self._tpath: str = ""
        self._suite_name: str = ""
        self._test_names: List[str] = []
        self._total_steps = 0

        self._tmp_dir: str = ""


    def init_probe(self):
        if self.ready: return
        self.ready = False
        path, tpath = self.config.project_path, self.config.tests_path
        if not os.path.isabs(path):
            logE("Test path not absolute")
            return

        suites = {}

        for (dirpath, dirnames, filenames) in os.walk(tpath):
            rel = os.path.relpath(dirpath, tpath)
            if os.sep not in rel: continue
            a, b = rel.split(os.sep)
            if a not in suites: suites[a] = {}
            if b not in suites[a]: suites[a][b] = []
            fs = suites[a][b]
            for fn in filenames:
                fs.append(fn)

        self.suites = suites
        self.ready = True

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

    def _checked_run(self):
        self.print_title()
        for test in self._test_names:
            runner = self._resolve_runner(test)
            runner.exec_simple()
        logI(f"Finished all {self._total_steps} steps")

    def _resolve_runner(self, test) -> TestRunner:
        factory =  self.runners["default"]
        steps = self.suites[self._suite_name][test]
        return factory(self._path, self._tpath, self._tmp_dir, self._suite_name, test, steps)

    def print_title(self):
        logI("=" * CONSOLE_WIDTH)
        title = f"{self._suite_name} (Total: " \
                f"{len(self._test_names)} Functions, {self._total_steps} Test Steps)"
        logI(center_text(title, CONSOLE_WIDTH))
        logI("=" * CONSOLE_WIDTH)

    def cleanup(self):
        if not self.config.debug:
            shutil.rmtree(self._tmp_dir)
            logP("Cleaned up temporary directory")
        else:
            logP("Temp directory left for debugging")


    def init_run_tests(self, path: str, test_path:str, suite: str, tests: List[str]):
        self._path = path
        self._tpath = test_path
        self._suite_name = suite
        self._test_names = tests

        suiteval = self.suites[suite]
        for test in tests:
            self._total_steps += len(suiteval[test])

    def run_tests(self, path: str, test_path:str, suite: str, tests: List[str]):
        self.init_run_tests(path, test_path, suite, tests)
        if not self.check_installs_once(path): return
        if not self.create_tmp_dir(path): return
        try:
            self._checked_run()
        finally:
            self.cleanup()

    def resolve_suite_and_tests(self, suite_no: Optional[int], tests: Optional[List[int]]):
        if suite_no is not None:
            if 0 <= suite_no < len(self.suites):
                suite_name, suite = list(self.suites.items())[suite_no]
            else:
                logE(f"Invalid suite number to run: {suite_no}")
                return None, []
        else:
            suite_name, suite = next(iter(self.suites.items()))

        if test is None:
            tests = range(len(suite))

        suite_vals = list(suite.items())
        test_names = []

        for test_no in tests:
            if not (0 <= test_no < len(suite)):
                logE(f"Invalid test number {test_no}. Aborting...")
                return False
            test_names.append(suite_vals[test_no].key)
            # self._total_steps += len(suite_vals[test_no])

        return suite_name, test_names

    def run_configured(self):
        self.init_probe()
        c = self.config
        suite, tests = self.resolve_suite_and_tests(c.suite_no, c.tests)
        self.run_tests(c.project_path, c.tests_path, suite, tests)

    def query_suites(self):
        assert self.ready
        return list(self.suites.keys())

    def query_funcs(self, name):
        assert self.ready
        suite = self.suites[name]
        return list(suite.keys())


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


class TkInterface(TextInterface):
    def __init__(self, executor: ProbingExecutor):
        global CONSOLE_WIDTH
        CONSOLE_WIDTH = 88

        self.executor = executor

        win = self.window = Tk()
        win.title("2MP3 Code Checker")
        win.resizable(False, False)

        self.top_frame = frame = Frame(win)

        svar = self.suite_var = tkinter.StringVar(frame)
        svar.set("Loading")
        svar.trace("w", self.on_suite_changed)
        smenu = self.suite_menu = OptionMenu(frame, svar, "Loading")
        smenu.pack(side=LEFT)

        tvar = self.test_var = tkinter.StringVar(frame)
        tvar.set("All")
        tmenu = self.test_menu = OptionMenu(frame, tvar, "All", "Blah")
        tmenu.pack(side=LEFT)

        self.init_buttons(frame)

        frame.pack()

        self.path = executor.config.project_path
        self.folder_var = StringVar()
        self.update_dir_label()
        self.folder = Label(win, textvariable=self.folder_var)
        self.folder.pack()

        self.log = ScrolledText(self.window, width=88, height=32,
                                selectbackground="lightgray", state=DISABLED)
        self.init_log()

        # Threading Objects
        self.log_queue = ThreadSafeItemStore()
        self.thread: Optional[threading.Thread] = None

        self.window.after(100, self.init_probe)


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

    def on_suite_changed(self, *args):
        assert args[2] == "w"
        self.update_tests(["All"] + self.executor.query_funcs(self.suite_var.get()))

    def update_menu(self, menu:Menu, var:StringVar, items: List[str], i):
        if not items: return
        # https://stackoverflow.com/a/17581364
        menu.delete(0, 'end')
        var.set(items[i])
        for item in items:
            # noinspection PyProtectedMember
            menu.add_command(label=item, command=self._setit(var, item))

    @staticmethod
    def _setit(var, item):
        def command():
            var.set(item)
        return command

    def update_suites(self, suites):
        self.update_menu(self.suite_menu["menu"], self.suite_var, suites, -1)

    def update_tests(self, tests):
        self.update_menu(self.test_menu["menu"], self.test_var, tests, 0)


    def update_dir_label(self):
        self.folder_var.set(f"Project Folder: {self.path}")

    def open_folder(self):
        self.path = askdirectory()
        if dir:
            self.update_dir_label()
            logI(f"Opened project folder {self.path}")

    def init_probe(self):
        self.executor.init_probe()
        self.update_suites(self.executor.query_suites())
        # tests are automatically updated in the reaction

    def check_code(self):
        if self.thread is not None:
            logW("There is still a process running! Wait until it finishes")
            return
        self.log_queue.clear()

        suite = self.suite_var.get()
        test = self.test_var.get()
        if test == "All":
            test = self.executor.query_funcs(suite)

        self.thread = threading.Thread(target=self.check_code_new_thread, args=(suite,test))
        self.thread.start()
        self.window.after(100, self.process_log_queue)

    def check_code_new_thread(self, suite, test):
        tpath = os.path.join(self.path, "tests")
        self.executor.run_tests(self.path, tpath, suite, test)
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
        if threading.current_thread() == threading.main_thread():
            self.log.configure(state=NORMAL)
            self.log.insert(END, str(s) + "\n", c)
            self.log.configure(state=DISABLED)
        else:
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
    project_path: str  # Must be the absolute path
    tests_path: str
    display_mode: str
    suite_no: Optional[int]
    tests: Optional[List[int]]
    debug: bool


def init_config():
    parser = argparse.ArgumentParser()

    parser.add_argument("-p",
        help="specify the root project directory, pwd if unset", metavar="PATH")

    parser.add_argument("-t", help="specify where to find the tests", metavar="PATH")

    parser.add_argument("-s", metavar="SUITE", type=int,
        help="specify the test suite (i.e. assignment) number. Last suite tested if unset.")

    parser.add_argument("-q", metavar="TEST", type=int, nargs="+",
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
        project_path = os.path.abspath(args.p)
    else:
        project_path = os.getcwd()

    if args.t:
        if os.path.isabs(s):
            tests_path = args.t
        else:
            tests_path = os.path.join(project_path, args.t)
    else:
        tests_path = os.path.join(project_path, "tests")

    return InitConfig(project_path, tests_path, args.m, args.s, args.q, args.d)

RUNNERS = {"default": GCCRunner}

def run_checker():
    config = init_config()
    executor = ProbingExecutor(config, RUNNERS)

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
            pass
        else:
            interface.run_blocking()

    elif display == "colored":
        interface = ColoredInterface()
        executor.run_configured()
    else:
        executor.run_configured()


if __name__ == "__main__":
    run_checker()

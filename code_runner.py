"""
Student code execution and testing module (MVP / Competition version).

WARNING:
This module uses subprocess with timeout for basic process isolation.
It is NOT a production-grade sandbox. Student code runs directly on the
host with the same permissions as the server process.

For production deployment, use Docker containers, nsjail, firejail,
or a similar OS-level isolation mechanism.
"""

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


TIMEOUT_SECONDS = 10
COMPILE_TIMEOUT_SECONDS = 30
MAX_OUTPUT_BYTES = 64 * 1024  # 64 KB per test case output


@dataclass
class TestCaseResult:
    index: int
    input_data: str
    expected: str
    actual: str
    status: str  # passed | wrong_answer | runtime_error | timeout | compile_error
    error_message: str = ""


@dataclass
class TestSuiteResult:
    total: int
    passed: int
    failed: int
    cases: List[TestCaseResult] = field(default_factory=list)
    compile_error: Optional[str] = None
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "compile_error": self.compile_error,
            "summary": self.summary,
            "cases": [
                {
                    "index": c.index,
                    "input": c.input_data,
                    "expected": c.expected,
                    "actual": c.actual,
                    "status": c.status,
                    "error_message": c.error_message,
                }
                for c in self.cases
            ],
        }


# ---------------------------------------------------------------------------
# Output comparison
# ---------------------------------------------------------------------------

NUMBER_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _normalize_strict(s: str) -> str:
    """Whitespace-tolerant normalization: strip per-line trailing space and trailing empty lines."""
    lines = s.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    lines = [line.rstrip() for line in lines]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _extract_numbers(text: str) -> list:
    """
    Extract all numeric tokens from text and normalize them.
    Integers and equivalent floats compare equal (e.g. '9' == '9.0').
    """
    out = []
    for token in NUMBER_RE.findall(text):
        try:
            value = float(token)
        except ValueError:
            continue
        if value.is_integer():
            out.append(str(int(value)))
        else:
            out.append(repr(value))
    return out


def _normalize_contains(s: str) -> str:
    """Collapse all whitespace into single spaces for substring matching."""
    return " ".join(s.split())


def compare_output(expected: str, actual: str, mode: str = "strict") -> bool:
    """
    Compare expected vs actual output using the selected mode.

    Modes
    -----
    strict       : per-line trailing whitespace removed, trailing empty lines ignored, line endings normalized
    numbers_only : extract numeric tokens from each side and compare sequence
                   (handles outputs like "计算结果是 9" vs "9")
    contains     : expected output (whitespace-normalized) must appear as a substring
                   inside actual output (whitespace-normalized)
    """
    if mode == "numbers_only":
        return _extract_numbers(expected) == _extract_numbers(actual)

    if mode == "contains":
        norm_expected = _normalize_contains(expected)
        norm_actual = _normalize_contains(actual)
        if not norm_expected:
            return True
        return norm_expected in norm_actual

    # default: strict
    return _normalize_strict(expected) == _normalize_strict(actual)


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

def detect_language(filename: str, language_hint: str = "") -> str:
    """Detect programming language from hint string or filename extension."""
    hint = language_hint.lower().strip()
    if hint:
        if "python" in hint or hint == "py":
            return "python"
        if "c++" in hint or "cpp" in hint or hint == "cxx":
            return "cpp"
        if hint == "c" and "c++" not in hint and "c#" not in hint:
            return "c"
        if "java" in hint:
            return "java"

    ext = Path(filename).suffix.lower()
    return {
        ".py": "python",
        ".c": "c",
        ".cpp": "cpp",
        ".cxx": "cpp",
        ".cc": "cpp",
        ".java": "java",
    }.get(ext, "")


# ---------------------------------------------------------------------------
# Compilation helper
# ---------------------------------------------------------------------------

def _compile(cmd: list, work_dir: str) -> Optional[str]:
    """Run compiler. Return error message on failure, None on success."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=COMPILE_TIMEOUT_SECONDS,
            cwd=work_dir,
        )
        if result.returncode != 0:
            return (result.stderr or f"Compilation failed with exit code {result.returncode}")[:2000]
        return None
    except subprocess.TimeoutExpired:
        return "Compilation timed out"
    except FileNotFoundError as exc:
        return f"Compiler not found: {exc}"


# ---------------------------------------------------------------------------
# Single test case runner
# ---------------------------------------------------------------------------

def _run_single(cmd: list, input_data: str, expected: str, index: int, work_dir: str, compare_mode: str = "strict") -> TestCaseResult:
    """Execute one test case and compare output."""
    try:
        result = subprocess.run(
            cmd,
            input=input_data,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            cwd=work_dir,
        )

        actual = result.stdout
        if len(actual.encode("utf-8", errors="replace")) > MAX_OUTPUT_BYTES:
            actual = actual[: MAX_OUTPUT_BYTES // 2] + "\n...[output truncated]"

        if result.returncode != 0:
            err = (result.stderr[:1000] if result.stderr else f"Process exited with code {result.returncode}")
            return TestCaseResult(index, input_data, expected, actual, "runtime_error", err)

        if compare_output(expected, actual, mode=compare_mode):
            return TestCaseResult(index, input_data, expected, actual, "passed")

        return TestCaseResult(index, input_data, expected, actual, "wrong_answer")

    except subprocess.TimeoutExpired:
        return TestCaseResult(
            index, input_data, expected, "",
            "timeout", f"Time limit exceeded (>{TIMEOUT_SECONDS}s)",
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_test_cases(code: str, filename: str, language_hint: str, test_cases: list, compare_mode: str = "strict") -> TestSuiteResult:
    """
    Run student code against provided test cases.

    Parameters
    ----------
    code : str
        Student source code.
    filename : str
        Original uploaded filename.
    language_hint : str
        Language string from the form (e.g. "Python", "C++").
    test_cases : list[dict]
        Each dict must contain ``input`` and ``expected_output`` keys.
    compare_mode : str
        Output comparison mode: "strict", "numbers_only", or "contains".

    Returns
    -------
    TestSuiteResult
    """
    if compare_mode not in ("strict", "numbers_only", "contains"):
        compare_mode = "strict"

    if not test_cases:
        return TestSuiteResult(0, 0, 0, summary="No test cases provided")

    lang = detect_language(filename, language_hint)
    if not lang:
        return TestSuiteResult(
            total=len(test_cases),
            passed=0,
            failed=len(test_cases),
            compile_error=f"Cannot detect language (file: {filename}, hint: {language_hint})",
            summary=f"0/{len(test_cases)} passed (unknown language)",
        )

    work_dir = tempfile.mkdtemp(prefix="student_code_")
    try:
        return _execute_in_workdir(code, filename, lang, test_cases, work_dir, compare_mode)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _execute_in_workdir(code: str, filename: str, lang: str, test_cases: list, work_dir: str, compare_mode: str = "strict") -> TestSuiteResult:
    """Prepare files, compile if needed, and run all test cases."""
    java_class = None

    # Write source file
    if lang == "java":
        match = re.search(r"public\s+class\s+(\w+)", code)
        java_class = match.group(1) if match else Path(filename).stem
        code_file = os.path.join(work_dir, f"{java_class}.java")
    else:
        code_file = os.path.join(work_dir, filename)

    with open(code_file, "w", encoding="utf-8") as fh:
        fh.write(code)

    # Compile step (C / C++ / Java)
    compile_error = None
    exe_path = os.path.join(work_dir, "a.out")

    if lang == "c":
        compile_error = _compile(["gcc", code_file, "-o", exe_path, "-lm"], work_dir)
    elif lang == "cpp":
        compile_error = _compile(["g++", code_file, "-o", exe_path, "-lm", "-std=c++17"], work_dir)
    elif lang == "java":
        compile_error = _compile(["javac", code_file], work_dir)

    if compile_error:
        cases = [
            TestCaseResult(i + 1, tc["input"], tc["expected_output"], "", "compile_error", compile_error)
            for i, tc in enumerate(test_cases)
        ]
        return TestSuiteResult(
            len(test_cases), 0, len(test_cases), cases, compile_error,
            f"0/{len(test_cases)} passed (compile error)",
        )

    # Build run command
    if lang == "python":
        run_cmd = ["python3", code_file]
    elif lang in ("c", "cpp"):
        run_cmd = [exe_path]
    elif lang == "java":
        run_cmd = ["java", "-cp", work_dir, java_class]
    else:
        run_cmd = []

    # Execute each test case
    results: List[TestCaseResult] = []
    passed = 0
    for i, tc in enumerate(test_cases):
        r = _run_single(run_cmd, tc["input"], tc["expected_output"], i + 1, work_dir, compare_mode)
        results.append(r)
        if r.status == "passed":
            passed += 1

    failed = len(test_cases) - passed
    return TestSuiteResult(
        len(test_cases), passed, failed, results,
        summary=f"{passed}/{len(test_cases)} passed",
    )

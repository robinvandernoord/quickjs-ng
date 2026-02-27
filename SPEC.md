# Porting Specification: quickjs → quickjs-ng

This document describes every change made to port the
[PetterS/quickjs](https://github.com/PetterS/quickjs) Python wrapper to the
actively maintained [quickjs-ng](https://github.com/quickjs-ng/quickjs) engine.

The reference project is the original `quickjs` Python package (PyPI: `quickjs`,
import: `import quickjs`). The ported project is `quickjs-ng` (PyPI:
`quickjs-ng`, import: `import quickjs`).

---

## 1. Upstream Engine Changes

The `upstream-quickjs` git submodule was changed from Fabrice Bellard's original
QuickJS to the quickjs-ng fork:

```
# .gitmodules
[submodule "upstream-quickjs"]
    path = upstream-quickjs
    url = https://github.com/quickjs-ng/quickjs
```

quickjs-ng is a community-maintained fork with ES2023+ support, performance
improvements, and ongoing bug fixes. It introduces several API and behavioral
changes that required updates to the C extension and test suite.

---

## 2. C Extension Changes (`module.c`)

### 2.1 `JS_NewClassID` signature change

The quickjs-ng API changed `JS_NewClassID` to require a `JSRuntime *` argument:

| Version     | Signature                                                |
|-------------|----------------------------------------------------------|
| Original    | `JSClassID JS_NewClassID(JSClassID *pclass_id)`          |
| quickjs-ng  | `JSClassID JS_NewClassID(JSRuntime *rt, JSClassID *pclass_id)` |

In the original wrapper, `JS_NewClassID` was called during module
initialization in `PyInit__quickjs`, where no `JSRuntime` exists yet:

```c
// BEFORE (PyInit__quickjs)
JS_NewClassID(&js_python_function_class_id);
```

The fix moves this call into `runtime_new`, where `self->runtime` is available,
and inserts it before the existing `JS_NewClass` call:

```c
// AFTER (runtime_new)
self->runtime = JS_NewRuntime();
JS_NewClassID(self->runtime, &js_python_function_class_id);
self->context = JS_NewContext(self->runtime);
JS_NewClass(self->runtime, js_python_function_class_id,
            &js_python_function_class);
```

The `PyInit__quickjs` function no longer calls `JS_NewClassID` at all.

### 2.2 i686 / 32-bit NaN-boxing fix

On 32-bit platforms (`INTPTR_MAX < INT64_MAX`), QuickJS enables NaN-boxing
(`JS_NAN_BOXING 1`), where `JSValue` is represented as a `uint64_t`.  In this
encoding, float64 values are stored by manipulating the upper 32 bits, and
`JS_VALUE_GET_TAG(v)` returns those raw upper 32 bits — which for float values
will **not** equal `JS_TAG_FLOAT64` (8).  Instead they are large bit-pattern
values that satisfy the predicate `JS_TAG_IS_FLOAT64(tag)`.

The original `quickjs_to_python` extracted the tag with `JS_VALUE_GET_TAG`,
so any float returned from QuickJS on i686 produced an `Unknown quickjs tag`
`TypeError` at the Python level.

The fix uses `JS_VALUE_GET_NORM_TAG` instead, which normalizes any
NaN-boxed float tag to the canonical `JS_TAG_FLOAT64` value.  On 64-bit
platforms (no NaN-boxing) `JS_VALUE_GET_NORM_TAG` is identical to
`JS_VALUE_GET_TAG`, so the change is safe everywhere:

```c
// BEFORE (module.c — quickjs_to_python)
int tag = JS_VALUE_GET_TAG(value);

// AFTER
int tag = JS_VALUE_GET_NORM_TAG(value);
```

**Affected tests (i686 only):**

| Test | Symptom |
|------|---------|
| `GetAndSet.test_set_get_float` | `TypeError: Unknown quickjs tag: -1072619858` |
| `GetAndSet.test_set_negative` | `TypeError: Unknown quickjs tag: 1074863790` |
| `JSONParsing.test_parse_json_simple` | `TypeError: Unknown quickjs tag: -1068695562` |
| `TypedArrays.test_float64array` | `TypeError: Unknown quickjs tag: -1072168970` |
| `ES2020Features.test_optional_chaining` | `TypeError: Unknown quickjs tag: -1068695562` |
| `FunctionHelper.test_identity` | `TypeError: Unknown quickjs tag: -1073741834` |
| `FunctionThreads.test_concurrent` | `TypeError: Unknown quickjs tag: -1054442330` |
| `FunctionThreads.test_concurrent_own_executor` | `TypeError: Unknown quickjs tag: -1054442330` |

### 2.3 Stack overflow error message

quickjs-ng changed the stack overflow error string from `"stack overflow"` to
`"Maximum call stack size exceeded"`. The `quickjs_exception_to_python` function
was updated to match both patterns so that the Python `StackOverflow` exception
is raised correctly regardless of which engine is in use:

```c
// BEFORE
if (strstr(cstring, "stack overflow") != NULL) {

// AFTER
if (strstr(cstring, "stack overflow") != NULL ||
    strstr(cstring, "call stack size exceeded") != NULL) {
```

---

## 3. Build System Changes (`setup.py`)

### 3.1 Removed C source files

quickjs-ng reorganized its source tree. Two files present in the original
QuickJS no longer exist:

| Removed file                  | Reason                                      |
|-------------------------------|---------------------------------------------|
| `upstream-quickjs/cutils.c`   | Merged into other source files in quickjs-ng |
| `upstream-quickjs/libbf.c`    | BigNum (`CONFIG_BIGNUM`) removed upstream    |

### 3.2 Added C source file

| Added file                    | Reason                                      |
|-------------------------------|---------------------------------------------|
| `upstream-quickjs/dtoa.c`     | New file in quickjs-ng for float conversion  |

### 3.3 Removed compile-time macros

| Removed macro      | Reason                                                  |
|--------------------|---------------------------------------------------------|
| `CONFIG_VERSION`   | quickjs-ng has no `VERSION` file; version is in the header |
| `CONFIG_BIGNUM`    | BigNum extension removed from quickjs-ng                |

### 3.4 Updated header list

The sdist header list was updated to match the quickjs-ng source tree — removed
`libbf.h` and `VERSION`, added `dtoa.h`.

### 3.5 Removed `long_description` and author metadata from `setup.py`

All package metadata was moved to `pyproject.toml`. The `setup()` call in
`setup.py` is now minimal, providing only `ext_modules`.

### 3.6 Windows MSVC compile flags

When building on Windows with MSVC, two changes are required:

1. **`/std:c11`** — MSVC defaults to C89 mode, which rejects C99 features
   used throughout `module.c` and the upstream QuickJS source: `for (int i…)`
   loop-variable declarations, mixed declarations and code, and designated
   initialisers in struct literals.  Adding `/std:c11` enables full C99/C11
   support.

2. **`-static`** link flag (Windows only) — static-links the MSVC runtime
   so the wheel does not depend on a specific MSVCRT DLL being present.

```python
if sys.platform == "win32":
    extra_link_args = ["-static"]
    extra_compile_args = ["/std:c11"]
else:
    extra_compile_args = ["-Werror=incompatible-pointer-types"]
```

### 3.7 Final `setup.py`

```python
_quickjs = Extension(
    '_quickjs',
    sources=get_c_sources(include_headers=("sdist" in sys.argv)),
    extra_compile_args=extra_compile_args,
    extra_link_args=extra_link_args)

setup(ext_modules=[_quickjs])
```

---

## 4. Build Backend Change (`pyproject.toml`)

The original project scaffolding used `hatchling` as the build backend.
Hatchling does not support building C extensions defined in `setup.py`.
The backend was changed to `setuptools`:

```toml
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"
```

Package discovery is explicit:

```toml
[tool.setuptools]
packages = ["quickjs"]
```

---

## 5. Package Naming

The project is published to PyPI as `quickjs-ng` but the Python package
directory is named `quickjs/` so that downstream code can do:

```python
import quickjs
```

This makes `quickjs-ng` a drop-in replacement for the original `quickjs`
package with no import changes required.

| Attribute          | Original                    | quickjs-ng                  |
|--------------------|-----------------------------|-----------------------------|
| PyPI name          | `quickjs`                   | `quickjs-ng`                |
| Import name        | `quickjs`                   | `quickjs`                   |
| Package directory  | `quickjs/`                  | `quickjs/`                  |
| C extension module | `_quickjs`                  | `_quickjs`                  |

---

## 6. Test Suite Changes

### 6.1 Test suite reorganization

The original project had a single monolithic test file `test_quickjs.py`.  All
tests were split and deduplicated into six logical files:

| File                         | Contents                                                       |
|------------------------------|----------------------------------------------------------------|
| `tests/test_callable.py`     | Python-callable-from-JS tests (`add_callable`)                 |
| `tests/test_context.py`      | Core `Context` API: eval, get/set, JSON, error handling, limits |
| `tests/test_js_features.py`  | ES2020–ES2023 features, async, generators, destructuring, typed arrays, RegExp, etc. |
| `tests/test_memory.py`       | Memory leak detection via `tracemalloc` (see §16)              |
| `tests/test_object.py`       | `Object` and `Function` wrapper tests                          |
| `tests/test_threading.py`    | Threading safety tests (see §17)                               |

### 6.2 Adapted test content

Three categories of changes were needed when porting tests from the original
`quickjs` project:

**Error message format** — quickjs-ng no longer quotes identifiers in
`ReferenceError` messages:

```python
# BEFORE
"ReferenceError: 'missing' is not defined"
# AFTER
"ReferenceError: missing is not defined"
```

**Backtrace format** — quickjs-ng includes column numbers in stack traces.
Assertions were relaxed to use prefix matching:

```python
# BEFORE
self.assertIn("at funcA (<input>:3)\n", msg)
# AFTER
self.assertIn("at funcA (<input>:3", msg)
```

**Stack overflow recursion limit** — the `test_deep_recursion` test was
completely redesigned to be reliable across all platforms and architectures
(Linux x86_64/i686, macOS arm64, Windows x86_64/i686):

```python
# BEFORE — relied on default 1 MB QuickJS stack; fragile across platforms
limit = 500

# AFTER — set an explicit 64 KB JS stack; 300 frames overflows on every arch
# (64-bit: overflows at ~89 frames; 32-bit i686: overflows at ~178 frames)
f.set_max_stack_size(64 * 1024)
with self.assertRaises(quickjs.StackOverflow):
    f(300)
# Restore to 256 KB to verify recovery; fits comfortably on all platforms
f.set_max_stack_size(256 * 1024)
self.assertEqual(f(50), 50)
```

The test uses `own_executor=True` so the `Function` runs on a dedicated
thread and the stack-size manipulation is isolated.

### 6.3 New tests — JS features (`tests/test_js_features.py`)

A comprehensive test file covering modern JavaScript features:

| Test class               | Features tested                                        |
|--------------------------|--------------------------------------------------------|
| `ES2020Features`         | Optional chaining, nullish coalescing, globalThis, Promise.allSettled, BigInt |
| `ES2021Features`         | Logical assignment, numeric separators, replaceAll, Promise.any, WeakRef |
| `ES2022Features`         | Class fields (public/private/static), `.at()`, Object.hasOwn, error cause, regex match indices, top-level await |
| `ES2023Features`         | findLast, toReversed, toSorted, toSpliced, `.with()`, hashbang comments |
| `AsyncAndPromises`       | async/await, error handling, promise chains, finally, for-await-of |
| `Generators`             | Basic generators, return values, yield delegation      |
| `Destructuring`          | Array, object, nested, rest elements, defaults         |
| `SpreadOperator`         | Array spread, object spread, function argument spread  |
| `TemplateLiterals`       | Basic templates, tagged templates, multiline           |
| `MapAndSet`              | Map, Set, WeakMap                                      |
| `ProxyAndReflect`        | Proxy get/set handlers, Reflect.ownKeys                |
| `Iterators`              | Symbol.iterator protocol, Array.from                   |
| `TypedArrays`            | Uint8Array, Float64Array, ArrayBuffer/DataView         |
| `RegExpFeatures`         | Named groups, dotAll flag, lookbehind, Unicode property escapes |
| `StringMethods`          | padStart/End, trimStart/End, matchAll, unicode         |
| `ObjectMethods`          | entries, fromEntries, values, Object.assign            |

### 6.4 New test file (`tests/test_threading.py`)

See [§17 — Threading Test Suite](#17-threading-test-suite-teststest_threadingpy) for full details.

---

## 7. Removed Files

Files from the original project that were not applicable to this port:

| File              | Reason                                                      |
|-------------------|-------------------------------------------------------------|
| `Dockerfile`      | Referenced nonexistent `quickjs_ng/foo.py`                  |
| `tox.ini`         | Redundant — CI matrix in GitHub Actions covers multi-version testing |
| `codecov.yaml`    | Not needed without Codecov integration                      |

---

## 8. Dependency Changes (`pyproject.toml`)

| Removed              | Reason                                               |
|----------------------|------------------------------------------------------|
| `deptry`             | Not useful for C extension projects                  |
| `tox-uv`             | `tox.ini` was removed                                |

---

## 9. Makefile

Rewritten for a C extension project using `uv`:

| Target               | Command                             | Purpose                           |
|----------------------|-------------------------------------|-----------------------------------|
| `make install`       | `uv sync && uv pip install -e .`    | Create venv, build C extension, install pre-commit hooks |
| `make check`         | Lock check, pre-commit, mypy        | Code quality                      |
| `make test`          | `pytest tests --cov`                | Run test suite with coverage      |
| `make build`         | `uv build`                          | Build sdist and wheel             |
| `make clean`         | Remove dist/, build/, .so, .o, coverage artifacts, wheelhouse/ | Clean all build artifacts |
| `make publish`       | `uv publish`                        | Publish to PyPI                   |

Key difference from the original Makefile: `uv pip install -e .` is required
to compile the C extension in-place for development.

`make clean` removes:
- `dist/`, `build/`, `*.egg-info/`, `wheelhouse/`
- All `*.so` and `*.o` files outside `.venv/`
- `.coverage` and `coverage.xml`

**Note on venv shebangs** — if the project directory is moved or renamed after
`make install`, the venv's script shebangs become stale (they embed the absolute
path at creation time).  Recreate with `rm -rf .venv && make install`.

---

## 10. GitHub Actions Workflows

### 10.1 Workflow overview

Two workflows were added under `.github/workflows/`:

| File                    | Trigger                          | Purpose                                |
|-------------------------|----------------------------------|----------------------------------------|
| `build.yml`             | `workflow_call`, `workflow_dispatch` | Build wheels + sdist and publish to PyPI |
| `check-upstream.yml`    | Daily cron (06:00 UTC), `workflow_dispatch` | Detect new upstream tags and trigger `build.yml` |

### 10.2 Upstream tag detection (`check-upstream.yml`)

Runs daily via cron.  Compares the current `upstream-quickjs` submodule commit
against the latest tag on `https://github.com/quickjs-ng/quickjs`:

```
current submodule SHA == latest tag SHA  →  no action
current submodule SHA != latest tag SHA  →  trigger build.yml with latest tag
```

The trigger uses `actions/github-script` to call `createWorkflowDispatch`,
passing the new tag as the `upstream_tag` input.

### 10.3 Version stamping (`build.yml`)

Before building, the version in `pyproject.toml` is updated automatically:

```bash
UPSTREAM_VER="${upstream_tag#v}"      # strip leading 'v', e.g. 0.12.1
CURRENT_BASE="${CURRENT_VER%.*}"      # strip patch, e.g. 0.12.1

if [ "$CURRENT_BASE" = "$UPSTREAM_VER" ]; then
    VERSION=$CURRENT_VER              # same upstream → keep wrapper patch
else
    VERSION=${UPSTREAM_VER}.1         # new upstream → reset patch to 1
fi
sed -i "s/^version = .*/version = \"$VERSION\"/" pyproject.toml
```

See [§15 — Version Scheme](#15-version-scheme) for the full versioning policy.

### 10.4 cibuildwheel build matrix

Wheels are built with `pypa/cibuildwheel@v2.23` across the following matrix:

| Runner          | Architectures     | Notes                              |
|-----------------|-------------------|------------------------------------||
| `ubuntu-latest` | x86_64            | manylinux + musllinux              |
| `ubuntu-latest` | i686              | `manylinux_2_28` image (GCC ≥ 8 for C99 label syntax) |
| `ubuntu-latest` | aarch64           | `manylinux_2_28` image; QEMU emulation via `docker/setup-qemu-action` |
| `windows-latest`| AMD64 (x86_64)    | MSVC with `/std:c11`               |
| `windows-latest`| x86 (i686)        | MSVC with `/std:c11`               |
| `macos-14`      | arm64             | Apple Silicon runner               |

`macos-13` (Intel x86_64) was removed — that runner image is deprecated and
no longer supported by GitHub Actions.

Python versions built: `cp310-*`, `cp311-*`, `cp312-*`, `cp313-*`, `cp314-*`.
Free-threaded builds (`cp313t-*`, `cp314t-*`) are **not** built.
`cp314-*` wheels are built while Python 3.14 remains a pre-release via the
`enable = ["cpython-prerelease"]` setting in `pyproject.toml`.

cibuildwheel configuration in `pyproject.toml`:

```toml
[tool.cibuildwheel]
before-build = "rm -rf {project}/build {project}/*.so {project}/_quickjs*"
test-requires = ["pytest"]
test-command = "pytest {project}/tests -q"
enable = ["cpython-prerelease"]
```

The `manylinux_2_28` image is specified via `CIBW_MANYLINUX_I686_IMAGE` and
`CIBW_MANYLINUX_AARCH64_IMAGE` environment variables in `build.yml`.  The
older `manylinux2014` image ships GCC 4.8 which rejects the C99 construct
`case X: { int y; … }` (a declaration after a label) used in `cutils.h`.

The `before-build` hook removes stale `.so` files that would otherwise be
picked up by setuptools from the host instead of being rebuilt inside the
build container.

### 10.5 Artifact upload and publish

Each matrix job uploads its wheels as a named artifact
(`wheels-<os>-<arch>`).  The `publish` job downloads all artifacts
(`merge-multiple: true`) into `dist/` and publishes to PyPI using
`pypa/gh-action-pypi-publish` with Trusted Publishing (OIDC, no API token
stored in secrets).  The `publish` job has `permissions: id-token: write`
which is the only configuration required on the GitHub side.

### 10.6 CI matrix for tests

The `main.yml` CI workflow runs `pytest` across Python 3.10–3.14 on Ubuntu,
Windows, and macOS.  The composite action `setup-python-env` sets
`allow-prereleases: true` on `actions/setup-python@v5` so that Python 3.14
(pre-release) can be installed during CI.

**Why two workflows?**

| Aspect | CI (`main.yml`) | Build wheels (`build.yml`) |
|--------|-----------------|----------------------------|
| Trigger | Every push + PR | Push to `main`/`devel`, `workflow_call`, `workflow_dispatch` |
| Speed | ~2 min per job | 2–60 min (aarch64 via QEMU) |
| What it builds | C extension via `uv pip install -e .` | Binary wheels via `cibuildwheel` inside Docker |
| Test environment | Native host Python | Exact manylinux/musllinux/Windows wheel environment |
| Purpose | Fast regression feedback | Produces publishable artifacts; validates the actual wheel |

Both are necessary: CI gives fast feedback on every push; Build wheels validates the exact published artifact in the exact target environment (manylinux containers, etc.) and handles PyPI publishing.

---

## 11. Documentation

| File                | Changes                                                    |
|---------------------|------------------------------------------------------------|
| `CONTRIBUTING.md`   | Simplified to match actual workflow with `uv` and `make`   |
| `docs/SPEC.md`      | This file — full porting specification                     |

---

## 12. Windows MSVC C Extension Fixes (`module.c`)

Building the C extension with MSVC required three fixes beyond the `/std:c11`
flag in `setup.py`:

### 12.1 `PyObject_HEAD` trailing semicolon

The `ObjectData` struct had a trailing semicolon after `PyObject_HEAD`:

```c
// BEFORE — invalid in C++ mode; also lint noise
typedef struct {
    PyObject_HEAD;
    RuntimeData *runtime_data;
    JSValue object;
} ObjectData;

// AFTER — correct for both C and C++ compilation
typedef struct {
    PyObject_HEAD
    RuntimeData *runtime_data;
    JSValue object;
} ObjectData;
```

`PyObject_HEAD` already expands to `PyObject ob_base;` — the extra semicolon
created an empty declaration which MSVC rejected as `C2059`.

### 12.2 Empty struct

MSVC's C mode (unlike GCC/Clang) rejects empty structs (`C2016`):

```c
// BEFORE — rejected by MSVC in C mode
struct module_state {};

// AFTER — dummy member satisfies the C standard requirement
struct module_state {
    int dummy;
};
```

### 12.3 C99 features require `/std:c11`

`module.c` uses several C99 features that MSVC's default C89 mode rejects:

| Feature | Example |
|---------|---------|
| `for`-loop variable declarations | `for (int i = 0; …)` |
| Mid-function variable declarations | `const int nargs = …;` after statements |
| Designated initialisers | `.tp_name = "…", .tp_basicsize = …` |

All are legal under C99/C11.  Adding `/std:c11` to `extra_compile_args` on
Windows resolves all these errors without any source changes.

---

## 13. Behavioral Differences Summary

For users migrating from the original `quickjs` package:

| Behavior                    | Original quickjs           | quickjs-ng                          |
|-----------------------------|----------------------------|-------------------------------------|
| Stack overflow message      | `"stack overflow"`         | `"Maximum call stack size exceeded"` |
| Default stack size          | 256 KB                     | 1 MB (`JS_DEFAULT_STACK_SIZE`)      |
| Error identifier quoting    | `'missing' is not defined` | `missing is not defined`            |
| Backtrace column numbers    | Not included               | Included (e.g. `<input>:3:21`)      |
| BigNum (`CONFIG_BIGNUM`)    | Enabled                    | Removed (BigInt still native)       |
| ES2023+ features            | Not available              | Supported                           |
| `JS_NewClassID` API         | 1 argument                 | 2 arguments (runtime + class ID)    |
| Worker thread stack (musl)  | 128 KB (system default)    | 8 MB (explicit, matches glibc)      |
| Threading documentation     | One-line note in README    | Dedicated section with patterns     |
| Threading tests             | 2 (`Function` only)        | 12 (`Function` + context-per-thread)|
| Free-threaded Python (t builds) | Not applicable        | Safe; GIL not relied upon           |
| i686 float return values    | N/A (no i686 wheels)       | Fixed via `JS_VALUE_GET_NORM_TAG`   |

---

## 13. musl / Alpine Stack Size Fix (`quickjs/__init__.py`)

### 13.1 Problem

The `Function` helper runs JavaScript on a dedicated `ThreadPoolExecutor`
worker thread.  On glibc-based systems the default thread stack is 8 MB,
but on musl-based systems (Alpine Linux, musllinux wheels) it is only
128 KB.  QuickJS's internal stack limit defaults to 1 MB
(`JS_DEFAULT_STACK_SIZE`).  When JS code recurses deeply — or the user
calls `set_max_stack_size` to raise the limit — the real C stack overflows
before QuickJS's guard can fire, causing a **segfault** instead of a
clean `StackOverflow` exception.

### 13.2 Fix

A `_create_executor()` helper was added to `quickjs/__init__.py` that
creates every `ThreadPoolExecutor` with an explicit 8 MB stack:

```python
_THREAD_STACK_SIZE = 8 * 1024 * 1024  # 8 MB, matches glibc default

def _create_executor() -> concurrent.futures.ThreadPoolExecutor:
    old = threading.stack_size()
    try:
        threading.stack_size(_THREAD_STACK_SIZE)
        pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix=prefix)
        # Force the worker to spawn now while the enlarged stack is active.
        pool.submit(lambda: None).result()
    finally:
        threading.stack_size(old)
    return pool
```

Key design decisions:

- **`threading.stack_size` is global** — it affects all threads created
  afterwards.  The helper saves and restores the previous value so that
  unrelated threads are not affected.
- **Eager worker spawn** — `ThreadPoolExecutor` creates threads lazily.
  A no-op `submit().result()` forces the worker to spawn immediately
  while the enlarged stack size is in effect.
- **Named threads** — each executor gets a unique
  `thread_name_prefix="quickjs-worker-N"` for debugging.

The class-level shared executor and the `own_executor=True` path in
`Function.__init__` both use `_create_executor()` instead of raw
`ThreadPoolExecutor(max_workers=1)`.

### 13.3 Original code (for comparison)

```python
# Original quickjs — no stack size handling
class Function:
    _threadpool = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def __init__(self, name, code, *, own_executor=False):
        if own_executor:
            self._threadpool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
```

---

## 14. Threading Model & Documentation

### 14.1 Threading model

QuickJS runtimes are **single-threaded by design**.  The `JSRuntime`
struct has no internal mutexes protecting its general state (GC lists,
atom tables, stack pointer, etc.).  The only mutex in QuickJS
(`js_atomics_mutex`) protects `SharedArrayBuffer` atomics, not the
runtime itself.

The C extension calls `JS_UpdateStackTop(rt)` in `prepare_call_js`
before every JS invocation.  This updates `rt->stack_top` to the
current thread's stack pointer — if a different OS thread calls into
the same runtime, the stack overflow guard sees a nonsensical value
and may segfault or silently corrupt state.

### 14.2 Safe patterns

| Pattern | How it works | Thread-safe | Overhead |
|---------|-------------|:-----------:|---------|
| **Context per thread** | Each thread creates its own `Context` (and therefore its own `JSRuntime`). No shared state. | ✅ | None |
| **`Function` helper** | Wraps a `Context` with a dedicated single-thread executor and `threading.Lock`. All JS runs on one thread. | ✅ | Small (executor dispatch) |
| **Shared `Context`** | Multiple threads use the same `Context`. | ❌ | — |

Adding a C-level mutex to `Context` was considered and rejected:

- It would **serialize** all JS execution, removing any parallelism benefit.
- Users might assume fine-grained safety and share mutable JS state,
  leading to subtle logic bugs.
- The context-per-thread pattern gives true parallelism with zero overhead.

### 14.3 Free-threaded Python (3.13t / 3.14t)

When the GIL is disabled the same threading rules apply.  The two safe
patterns (`Function` helper and context-per-thread) remain correct because
they already serialize access to each JS runtime independently of the GIL.
The package does not rely on the GIL for thread-safety — `prepare_call_js`
explicitly releases it before every JS call, and `end_call_js` re-acquires
it afterwards.  These calls become no-ops or use lighter-weight mechanisms
on free-threaded builds but do not cause crashes.

---

## 15. Version Scheme

The wrapper version follows the format `X.Y.Z.P`:

| Component | Meaning                                         | Example |
|-----------|-------------------------------------------------|---------|
| `X.Y.Z`   | Matches the upstream quickjs-ng tag (minus `v`) | `0.12.1` |
| `P`        | Wrapper patch version; starts at `1` for each new upstream release | `1` |

Examples:

| Scenario                                  | Result         |
|-------------------------------------------|----------------|
| First build against upstream `v0.12.1`    | `0.12.1.1`     |
| Second wrapper-only fix for `v0.12.1`     | `0.12.1.2`     |
| Build after upstream bumps to `v0.12.2`   | `0.12.2.1`     |

The version in `pyproject.toml` is the source of truth.  It is updated
automatically by the `build.yml` workflow before each build; see
[§10.3 — Version stamping](#103-version-stamping-buildyml).

---

## 16. Memory Leak Test Migration

### 16.1 Original `check_memory.py`

The original project included a top-level `check_memory.py` script that
detected memory leaks using `tracemalloc`.  It worked by re-running the
entire `unittest` test suite a second time inside a `tracemalloc` capture
window:

```python
# Original approach — re-discovers and runs the full test suite
loader = unittest.TestLoader()
suite = loader.discover('.', pattern='test_*.py')
...
```

This caused two problems in CI:

1. **Recursive discovery** — when run from the project root via cibuildwheel's
   `test-command`, `unittest.discover` would find and re-execute every test
   file, including itself, causing infinite recursion or double-execution.
2. **Not pytest-compatible** — `pytest` would not collect it as a test,
   so it was excluded with `--ignore=tests/test_memory.py` in the
   cibuildwheel config, meaning the leak check never ran in CI.

### 16.2 Rewritten `tests/test_memory.py`

The check was rewritten as a standard pytest test function that directly
exercises the key quickjs APIs inside a `tracemalloc` window:

```python
def _exercise_quickjs():
    ctx = quickjs.Context()
    ctx.eval("40 + 2")
    # ... more API calls ...
    del ctx

def test_no_memory_leak():
    _exercise_quickjs()          # warm-up (JIT caches, etc.)
    tracemalloc.start(25)
    gc.collect()
    snapshot1 = tracemalloc.take_snapshot().filter_traces(_filters)
    _exercise_quickjs()
    gc.collect()
    snapshot2 = tracemalloc.take_snapshot().filter_traces(_filters)
    tracemalloc.stop()
    leaked = [s for s in snapshot2.compare_to(snapshot1, "traceback")
              if s.size_diff > 0]
    assert not leaked
```

Key design decisions:

- **Direct API exercise** — no test discovery; avoids recursion and is
  self-contained.
- **Warm-up pass** — the first `_exercise_quickjs()` call before
  `tracemalloc.start` lets one-time allocations (module import caches,
  internal atom tables) settle so they do not appear as leaks.
- **Filters** — `tracemalloc` traces are filtered to the `quickjs/` and
  `_quickjs` modules only, ignoring Python-internal allocations.
- **`--ignore` removed** — the cibuildwheel `test-command` no longer
  excludes the memory test; it runs as part of the normal `pytest` suite.

---

## 17. Threading Test Suite (`tests/test_threading.py`)

### 17.1 Existing tests (from original project)

The original project had two `Function`-level threading tests in
`test_quickjs.py`.  These were extracted into a dedicated
`tests/test_threading.py` file as the `FunctionThreads` class:

| Test | Purpose |
|------|---------|
| `test_concurrent` | Proves `Function` is safe when called from multiple threads via a shared executor |
| `test_concurrent_own_executor` | Same, but with `own_executor=True` for separate `Function` instances |

### 17.2 New tests — `ContextPerThread` class

A new test class was added with 10 tests exercising the recommended
context-per-thread pattern.  Each test runs a `target` function in
8 parallel threads (configurable via `NUM_THREADS`), each performing
50 iterations (`ITERATIONS`).  A `_run_in_threads` helper propagates
assertions from any thread.

| Test | What it exercises |
|------|-------------------|
| `test_eval_basic` | `eval()` with arithmetic across threads |
| `test_get_set` | `get()`/`set()` global variable isolation (uses `thread.name` to avoid JS int truncation of large thread idents) |
| `test_function_calls` | Define and call JS functions per thread |
| `test_add_callable` | Register and invoke Python→JS callables per thread |
| `test_parse_json` | `parse_json` + `.json()` roundtrip per thread |
| `test_memory_and_gc` | `memory()` dict inspection and `gc()` per thread |
| `test_resource_limits` | Independent `set_memory_limit`, `set_time_limit`, `set_max_stack_size` per thread |
| `test_many_contexts_concurrent` | 20 threads × 20 computations with full result verification |
| `test_context_isolation_across_threads` | `threading.Barrier`-synchronized proof that globals don't leak between contexts |
| `test_pending_jobs_per_thread` | `Promise.resolve` + `execute_pending_job` per thread |

### 17.3 Design notes

- **Thread name instead of thread ident** — `threading.current_thread().ident`
  can exceed JavaScript's safe integer range (2^53) on 64-bit Linux, causing
  silent truncation when stored via `ctx.set()`.  Tests use
  `threading.current_thread().name` (a string) instead.
- **No shared state** — each test creates contexts inside the thread function,
  verifying that independent runtimes work correctly in parallel.
- **Barrier synchronization** — `test_context_isolation_across_threads` uses
  a `threading.Barrier` to force all threads to set their value before any
  thread reads, maximizing the chance of detecting cross-context leakage.

---

## 18. Type Annotations & mypy (`quickjs/__init__.py`, `_quickjs.pyi`)

### 18.1 Problem

Running `make check` (which includes `uv run mypy`) produced 16 errors:

- `import-not-found` — mypy could not locate the C extension `_quickjs` and
  had no stub to fall back on.
- `no-untyped-def` — several methods in `quickjs/__init__.py` lacked full
  type annotations.
- `valid-type` — `Object` and `Context` are module-level names assigned from
  the C extension (i.e. they are *values*, not type aliases), so mypy rejected
  them when used as type hints in `-> Object` / `Tuple[Context, Object]`.
- `no-any-return` — methods declared `-> None` used `return
  self._context.set_X()`, and `memory()` returned an untyped `Any`.

### 18.2 Stub file (`_quickjs.pyi`)

A PEP 484 stub file was created at the project root as `_quickjs.pyi`.
mypy resolves stubs by looking for `<module>.pyi` alongside the module,
and the C extension `.so` lives at the project root, so the stub must also
live there (not inside the `quickjs/` package directory).

```python
# _quickjs.pyi
from typing import Any

class Object:
    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...
    def json(self) -> str: ...

class JSException(Exception): ...
class StackOverflow(JSException): ...

class Context:
    globalThis: Object
    def eval(self, code: str, *args: Any, **kwargs: Any) -> Any: ...
    def module(self, code: str, *args: Any, **kwargs: Any) -> Any: ...
    def get(self, name: str) -> Any: ...
    def set(self, name: str, value: Any) -> None: ...
    def parse_json(self, s: str) -> Any: ...
    def add_callable(self, global_name: str, callable: Any) -> None: ...
    def set_memory_limit(self, limit: int) -> None: ...
    def set_time_limit(self, limit: float) -> None: ...
    def set_max_stack_size(self, limit: int) -> None: ...
    def memory(self) -> dict[str, Any]: ...
    def gc(self) -> None: ...
    def execute_pending_job(self) -> bool: ...

def test() -> Any: ...
```

### 18.3 `mypy_path` in `pyproject.toml`

`mypy_path = "."` was added to `[tool.mypy]` so mypy searches the project
root for stubs and source files:

```toml
[tool.mypy]
files = ["quickjs"]
mypy_path = "."
disallow_untyped_defs = true
...
```

Without this, mypy only searches `sys.path` and the `quickjs/` package
directory itself, and would never find a stub at the project root.

### 18.4 Annotation fixes in `quickjs/__init__.py`

| Location | Change |
|----------|--------|
| `from typing import ...` | Added `Any` to imports |
| `test()` | Added `-> Any` return type |
| `Function.__init__` | `own_executor=False` → `own_executor: bool = False` |
| `Function.__call__` | `*args` → `*args: Any`, `run_gc=True` → `run_gc: bool = True`, added `-> Any` |
| `set_memory_limit` | Added `limit: int` and `-> None`; removed `return` (was `return self._context.set_memory_limit(limit)`) |
| `set_time_limit` | Added `limit: float` and `-> None`; removed `return` |
| `set_max_stack_size` | Added `limit: int` and `-> None`; removed `return` |
| `memory()` | Added `-> dict[str, Any]`; used explicit typed local variable to avoid `no-any-return` |
| `gc()` | Added `-> None` |
| `execute_pending_job` | Wrapped return in `bool(...)` to satisfy `-> bool` (C extension returns `Any`) |
| `globalThis` property | Changed `-> Object` to `-> _quickjs.Object` (module attribute, not type alias) |
| `_compile` | Changed `Tuple[Context, Object]` to `Tuple[_quickjs.Context, _quickjs.Object]` |
| `_call` | `*args` → `*args: Any`, `run_gc=True` → `run_gc: bool = True`, added `-> Any` |
| `convert_arg` (inner) | Added `arg: Any` and `-> Any` |

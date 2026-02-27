# quickjs-ng

[![Build status](https://img.shields.io/github/actions/workflow/status/genotrance/quickjs-ng/main.yml?branch=main)](https://github.com/genotrance/quickjs-ng/actions/workflows/main.yml?query=branch%3Amain)
[![License](https://img.shields.io/github/license/genotrance/quickjs-ng)](https://img.shields.io/github/license/genotrance/quickjs-ng)

Python wrapper around [quickjs-ng](https://github.com/quickjs-ng/quickjs), the actively maintained fork of the [QuickJS](https://bellard.org/quickjs/) JavaScript engine.

This is a drop-in replacement for the archived [quickjs](https://github.com/PetterS/quickjs) Python package — `import quickjs` works unchanged.

## Installation

```bash
pip install quickjs-ng
```

## Usage

```python
import quickjs

# Evaluate expressions
ctx = quickjs.Context()
ctx.eval("1 + 2")  # => 3

# Call JS functions from Python
ctx.eval("function add(a, b) { return a + b; }")
add = ctx.get("add")
add(3, 4)  # => 7

# Call Python functions from JS
ctx.add_callable("py_add", lambda a, b: a + b)
ctx.eval("py_add(3, 4)")  # => 7

# Use the Function helper for thread-safe execution
f = quickjs.Function("f", "function f(x) { return x * 2; }")
f(21)  # => 42

# Resource limits
ctx.set_memory_limit(1024 * 1024)  # 1 MB
ctx.set_time_limit(5)              # 5 seconds of CPU time
ctx.set_max_stack_size(512 * 1024) # 512 KB stack
```

## Development

Requires a C compiler and [uv](https://docs.astral.sh/uv/).

```bash
git clone --recurse-submodules https://github.com/genotrance/quickjs-ng.git
cd quickjs-ng
make install
make test
```

Available `make` targets:

| Target              | Description                                          |
|---------------------|------------------------------------------------------|
| `make install`      | Create venv, build C extension, install pre-commit   |
| `make test`         | Run tests with coverage                              |
| `make check`        | Run linters and type checking                        |
| `make build`        | Build sdist and wheel                                |
| `make clean`        | Remove build artifacts                               |
| `make publish`      | Publish to PyPI                                      |

## Threading

Each `Context` owns an isolated QuickJS runtime — there is no shared state between
contexts. However, a single `Context` instance is **not thread-safe** and must not be
used from multiple threads (even non-concurrently).

**Recommended patterns:**

- **Context per thread** — create a separate `Context` in each thread. No locking
  required, no overhead, full parallelism:

  ```python
  import threading, quickjs

  def worker():
      ctx = quickjs.Context()
      ctx.eval("function add(a, b) { return a + b; }")
      print(ctx.get("add")(3, 4))

  threads = [threading.Thread(target=worker) for _ in range(4)]
  for t in threads:
      t.start()
  ```

- **`Function` helper** — wraps a `Context` with a dedicated worker thread and lock,
  making it safe to call from any thread. Convenient when you only need to invoke a
  single JS function:

  ```python
  f = quickjs.Function("f", "function f(x) { return x * 2; }")
  # safe to call f(21) from any thread
  ```

| Pattern | Thread-safe | Overhead | Shared JS state |
|---------|:-----------:|----------|:---------------:|
| Context per thread | ✅ | None | No |
| `Function` helper | ✅ | Small (executor dispatch) | No |
| Shared `Context` | ❌ | — | — |

**Free-threaded Python (3.14t+):** The same rules apply. The `Function`
helper and context-per-thread patterns remain safe because they already
serialize access to each JS runtime. The GIL was never relied upon for
thread-safety within this package.

## Platform notes

### musl / Alpine Linux

The `quickjs.Function` helper runs JavaScript on a background thread.  On
musl-based systems (Alpine, musllinux) the default thread stack is only 128 KB,
whereas QuickJS's internal stack limit defaults to 1 MB.  This wrapper
automatically creates worker threads with an 8 MB stack (matching glibc
defaults) so that `set_max_stack_size` and deep recursion work correctly on all
platforms.

## Versioning

This wrapper tracks [upstream quickjs-ng](https://github.com/quickjs-ng/quickjs) releases.
The version number is `X.Y.Z.P` where `X.Y.Z` matches the upstream quickjs-ng tag and `P` is the
patch version for this wrapper (starts at 1 for each new upstream release).

Wheels are built automatically when a new upstream tag is detected.

## Acknowledgments

This project is a fork of [quickjs](https://github.com/PetterS/quickjs) by
[Petter Strandmark](https://github.com/PetterS). Thank you for the excellent
foundation — the original design of the C bindings, the `Function` thread-safety
wrapper, and the overall API shape are all his work.

## Improvements over the original `quickjs` package

**Engine:**

- Based on **quickjs-ng** instead of the original Bellard QuickJS — actively maintained with ES2023+ features, bug fixes, and performance improvements.
- `BigInt` is supported natively; the legacy BigNum (`CONFIG_BIGNUM`) extension has been removed upstream.
- Stack overflow errors are reported as `"Maximum call stack size exceeded"` instead of `"stack overflow"`.
- Error messages and stack traces may differ slightly (e.g. column numbers in backtraces).

**Python bindings:**

- **musl / Alpine fix** — `Function` worker threads are created with an 8 MB stack (matching glibc defaults) so that `set_max_stack_size` and deep recursion work correctly on musl-based systems where the default 128 KB stack is too small.
- **`JS_NewClassID` per-runtime** — class IDs are registered on each runtime instead of globally, matching the quickjs-ng API change.
- **Stack overflow detection** — `quickjs_exception_to_python` now also matches the `"call stack size exceeded"` string used by quickjs-ng, in addition to the original `"stack overflow"`.

**Build & tooling:**

- Migrated from **Poetry** to **uv** + **setuptools** for dependency management and building.
- Modern **Makefile** with `install`, `test`, `check`, `build`, `clean`, and `publish` targets.
- **CI matrix** via GitHub Actions — tests run on Ubuntu, Windows, and macOS across Python 3.10–3.14.
- **Pre-commit hooks**, **ruff** linter/formatter, **mypy** type checking, and **pytest-cov** coverage.
- **cibuildwheel** configuration for automated wheel builds.
- Requires **Python ≥ 3.10** (original supported ≥ 3.8).

**Documentation & tests:**

- Comprehensive threading documentation and guidance (context-per-thread pattern).
- Expanded test suite organized into separate modules (`test_context`, `test_object`, `test_callable`, `test_threading`, `test_js_features`, `test_memory`).

## License

MIT

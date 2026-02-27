# Contributing to quickjs-ng

Contributions are welcome! Report bugs or request features at https://github.com/genotrance/quickjs-ng/issues.

## Getting started

Prerequisites: a C compiler, [Git](https://git-scm.com/), and [uv](https://docs.astral.sh/uv/).

```bash
git clone --recurse-submodules git@github.com:YOUR_NAME/quickjs-ng.git
cd quickjs-ng
make install
```

This creates a virtual environment, builds the C extension, and installs pre-commit hooks.

## Development workflow

1. Create a feature branch: `git checkout -b my-feature`
2. Make changes and add tests in `tests/`.
3. Run checks and tests:

```bash
make check
make test
```

4. Commit and push, then open a pull request.

## Pull request guidelines

- Include tests for new functionality.
- All CI checks must pass (linting, tests across Python 3.10–3.14).
- Update `README.md` if adding user-facing features.

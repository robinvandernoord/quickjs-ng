import sys

from setuptools import Extension, setup

extra_compile_args: list[str] = []
extra_link_args: list[str] = []

if sys.platform == "win32":
    extra_link_args = ["-static"]
    extra_compile_args = ["/std:c11"]  # C99 for-loop var declarations, etc.
else:
    extra_compile_args = ["-Werror=incompatible-pointer-types"]


def get_c_sources(include_headers=False):
    sources = [
        "module.c",
        "upstream-quickjs/dtoa.c",
        "upstream-quickjs/libregexp.c",
        "upstream-quickjs/libunicode.c",
        "upstream-quickjs/quickjs.c",
    ]
    if include_headers:
        sources += [
            "upstream-quickjs/cutils.h",
            "upstream-quickjs/dtoa.h",
            "upstream-quickjs/libregexp-opcode.h",
            "upstream-quickjs/libregexp.h",
            "upstream-quickjs/libunicode-table.h",
            "upstream-quickjs/libunicode.h",
            "upstream-quickjs/list.h",
            "upstream-quickjs/quickjs-atom.h",
            "upstream-quickjs/quickjs-opcode.h",
            "upstream-quickjs/quickjs.h",
        ]
    return sources


_quickjs = Extension(
    "_quickjs",
    # HACK.
    # See https://github.com/pypa/packaging-problems/issues/84.
    sources=get_c_sources(include_headers=("sdist" in sys.argv)),
    extra_compile_args=extra_compile_args,
    extra_link_args=extra_link_args,
)

setup(ext_modules=[_quickjs])

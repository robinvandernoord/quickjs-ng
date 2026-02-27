"""Tests for calling Python functions from JS and JS functions from Python."""

import gc
import unittest

import quickjs


class CallIntoPython(unittest.TestCase):
    def setUp(self):
        self.ctx = quickjs.Context()

    def test_make_function(self):
        self.ctx.add_callable("f", lambda x: x + 2)
        self.assertEqual(self.ctx.eval("f(40)"), 42)
        self.assertEqual(self.ctx.eval("f.name"), "f")

    def test_make_two_functions(self):
        for i in range(10):
            self.ctx.add_callable("f", lambda x, i=i: i + x + 2)
            self.ctx.add_callable("g", lambda x, i=i: i + x + 40)
            f = self.ctx.get("f")
            g = self.ctx.get("g")
            self.assertEqual(f(40) - i, 42)
            self.assertEqual(g(2) - i, 42)
            self.assertEqual(self.ctx.eval("((f, a) => f(a))")(f, 40) - i, 42)

    def test_make_function_call_from_js(self):
        self.ctx.add_callable("f", lambda x: x + 2)
        g = self.ctx.eval("""(
            function() {
                return f(20) + 20;
            }
        )""")
        self.assertEqual(g(), 42)

    def test_python_function_raises(self):
        def error(a):
            raise ValueError("A")

        self.ctx.add_callable("error", error)
        with self.assertRaisesRegex(quickjs.JSException, "Python call failed"):
            self.ctx.eval("error(0)")

    def test_python_function_not_callable(self):
        with self.assertRaisesRegex(TypeError, "Argument must be callable."):
            self.ctx.add_callable("not_callable", 1)

    def test_python_function_no_slots(self):
        for i in range(2**16):
            self.ctx.add_callable(f"a{i}", lambda i=i: i + 1)
        self.assertEqual(self.ctx.eval("a0()"), 1)
        self.assertEqual(self.ctx.eval(f"a{2**16 - 1}()"), 2**16)

    def test_function_after_context_del(self):
        def make():
            ctx = quickjs.Context()
            ctx.add_callable("f", lambda: 1)
            f = ctx.get("f")
            del ctx
            return f

        gc.collect()
        f = make()
        self.assertEqual(f(), 1)

    def test_python_function_unwritable(self):
        self.ctx.eval("""
            Object.defineProperty(globalThis, "obj", {
                value: "test",
                writable: false,
            });
        """)
        with self.assertRaisesRegex(TypeError, "Failed adding the callable."):
            self.ctx.add_callable("obj", lambda: None)

    def test_python_function_is_function(self):
        self.ctx.add_callable("f", lambda: None)
        self.assertTrue(self.ctx.eval("f instanceof Function"))
        self.assertTrue(self.ctx.eval("typeof f === 'function'"))

    def test_make_function_two_args(self):
        def concat(a, b):
            return a + b

        self.ctx.add_callable("concat", concat)
        result = self.ctx.eval("concat(40, 2)")
        self.assertEqual(result, 42)

        concat = self.ctx.get("concat")
        result = self.ctx.eval("((f, a, b) => 22 + f(a, b))")(concat, 10, 10)
        self.assertEqual(result, 42)

    def test_make_function_two_string_args(self):
        """Without the JS_DupValue in js_c_function, this test crashes."""

        def concat(a, b):
            return a + "-" + b

        self.ctx.add_callable("concat", concat)
        concat = self.ctx.get("concat")
        result = concat("aaa", "bbb")
        self.assertEqual(result, "aaa-bbb")

    def test_can_eval_in_same_context(self):
        self.ctx.add_callable("f", lambda: 40 + self.ctx.eval("1 + 1"))
        self.assertEqual(self.ctx.eval("f()"), 42)

    def test_can_call_in_same_context(self):
        inner = self.ctx.eval("(function() { return 42; })")
        self.ctx.add_callable("f", lambda: inner())
        self.assertEqual(self.ctx.eval("f()"), 42)

    def test_delete_function_from_inside_js(self):
        self.ctx.add_callable("f", lambda: None)
        # Segfaults if js_python_function_finalizer does not handle threading
        # states carefully.
        self.ctx.eval("delete f")
        self.assertIsNone(self.ctx.get("f"))

    def test_invalid_argument(self):
        self.ctx.add_callable("p", lambda: 42)
        self.assertEqual(self.ctx.eval("p()"), 42)
        with self.assertRaisesRegex(quickjs.JSException, "Python call failed"):
            self.ctx.eval("p(1)")
        with self.assertRaisesRegex(quickjs.JSException, "Python call failed"):
            self.ctx.eval("p({})")

    def test_time_limit_disallowed(self):
        self.ctx.add_callable("f", lambda x: x + 2)
        self.ctx.set_time_limit(1000)
        with self.assertRaises(quickjs.JSException):
            self.ctx.eval("f(40)")

    def test_conversion_failure_does_not_raise_system_error(self):
        # https://github.com/PetterS/quickjs/issues/38

        def test_list():
            return [1, 2, 3]

        self.ctx.add_callable("test_list", test_list)
        with self.assertRaises(quickjs.JSException):
            # With incorrect error handling, this (safely) made Python raise a SystemError
            # instead of a JS exception.
            self.ctx.eval("test_list()")

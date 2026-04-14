"""Sample git diffs for testing."""

# Simple Python file diff
SAMPLE_PYTHON_DIFF = """diff --git a/test.py b/test.py
index abc123..def456 100644
--- a/test.py
+++ b/test.py
@@ -1,5 +1,8 @@
 def hello():
-    print("Hello")
+    print("Hello World")
+
+def goodbye():
+    print("Goodbye")

 if __name__ == "__main__":
     hello()
+    goodbye()
"""

# Multiple files diff
SAMPLE_MULTI_FILE_DIFF = """diff --git a/file1.py b/file1.py
index abc123..def456 100644
--- a/file1.py
+++ b/file1.py
@@ -1,3 +1,4 @@
 def func1():
     pass
+    # New comment

diff --git a/file2.py b/file2.py
new file mode 100644
index 000000..xyz789
--- /dev/null
+++ b/file2.py
@@ -0,0 +1,5 @@
+def func2():
+    \'\'\'New function.\'\'\'
+    x = 1
+    y = 2
+    return x + y
"""

# Diff with deletions
SAMPLE_DELETION_DIFF = """diff --git a/old_code.py b/old_code.py
index abc123..def456 100644
--- a/old_code.py
+++ b/old_code.py
@@ -1,10 +1,5 @@
 def useful_function():
     return True

-def deprecated_function():
-    # This is old code
-    return False
-
 def another_function():
     return None
"""

# Large diff (for performance testing)
SAMPLE_LARGE_DIFF = """diff --git a/large_file.py b/large_file.py
index abc123..def456 100644
--- a/large_file.py
+++ b/large_file.py
@@ -1,10 +1,110 @@
 # Large file with many changes
 """ + "\n".join([f"+    line_{i} = {i}" for i in range(1, 101)]) + """
"""

# Diff with security issues
SAMPLE_SECURITY_DIFF = """diff --git a/insecure.py b/insecure.py
index abc123..def456 100644
--- a/insecure.py
+++ b/insecure.py
@@ -1,5 +1,12 @@
 import os
+import subprocess

 def process_user_input(user_input):
-    return user_input.strip()
+    # Security issue: command injection
+    result = subprocess.call(user_input, shell=True)
+
+    # Security issue: hardcoded password
+    password = "admin123"
+
+    # Security issue: SQL injection
+    query = f"SELECT * FROM users WHERE name = '{user_input}'"
+    return result
"""

# Diff with high cyclomatic complexity
SAMPLE_COMPLEX_DIFF = """diff --git a/complex.py b/complex.py
index abc123..def456 100644
--- a/complex.py
+++ b/complex.py
@@ -1,5 +1,25 @@
 def simple():
     return True
+
+def complex_function(a, b, c, d, e):
+    if a > 0:
+        if b > 0:
+            if c > 0:
+                if d > 0:
+                    if e > 0:
+                        return 1
+                    elif e < 0:
+                        return 2
+                    else:
+                        return 3
+                elif d < 0:
+                    return 4
+            elif c < 0:
+                return 5
+        elif b < 0:
+            return 6
+    elif a < 0:
+        return 7
+    else:
+        return 8
"""

# Diff with lint disables
SAMPLE_LINT_DISABLE_DIFF = """diff --git a/linted.py b/linted.py
index abc123..def456 100644
--- a/linted.py
+++ b/linted.py
@@ -1,3 +1,15 @@
 def normal_function():
     return True
+
+def function_with_disables():
+    # pylint: disable=line-too-long
+    very_long_line = "This is a very long line that would normally trigger a lint warning but is disabled"
+
+    # noqa: E501
+    another_long_line = "Another long line with noqa"
+
+    # type: ignore
+    problematic_type = get_value()  # type: ignore
+
+    return very_long_line + another_long_line
"""

# Empty diff
SAMPLE_EMPTY_DIFF = ""

# Binary file diff
SAMPLE_BINARY_DIFF = """diff --git a/image.png b/image.png
index abc123..def456 100644
Binary files a/image.png and b/image.png differ
"""

# Diff with non-Python files
SAMPLE_MIXED_DIFF = """diff --git a/code.py b/code.py
index abc123..def456 100644
--- a/code.py
+++ b/code.py
@@ -1,3 +1,4 @@
 def hello():
     print("Hello")
+    return True

diff --git a/README.md b/README.md
index xyz789..uvw456 100644
--- a/README.md
+++ b/README.md
@@ -1,2 +1,3 @@
 # Project
 This is a test project
+With additional documentation
"""

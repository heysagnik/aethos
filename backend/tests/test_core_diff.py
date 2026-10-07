from core.diff import parse_unified_diff

SAMPLE = """\
diff --git a/app/util.py b/app/util.py
index 111..222 100644
--- a/app/util.py
+++ b/app/util.py
@@ -1,4 +1,5 @@
 import os
+import sys

 def f():
-    return 1
+    return 2
@@ -20,3 +21,4 @@ def g():
     a = 1
     b = 2
+    c = 3
     return a
diff --git a/new.txt b/new.txt
new file mode 100644
--- /dev/null
+++ b/new.txt
@@ -0,0 +1,2 @@
+hello
+world
\\ No newline at end of file
diff --git a/old.py b/old.py
deleted file mode 100644
--- a/old.py
+++ /dev/null
@@ -1,1 +0,0 @@
-x = 1
diff --git a/logo.png b/logo.png
index 1..2 100644
Binary files a/logo.png and b/logo.png differ
diff --git a/a.py b/b.py
similarity index 90%
rename from a.py
rename to b.py
--- a/a.py
+++ b/b.py
@@ -1 +1 @@
-x
+y
"""


def test_parses_files_status_and_paths():
    files = {f.path: f for f in parse_unified_diff(SAMPLE)}
    assert set(files) == {"app/util.py", "new.txt", "old.py", "logo.png", "b.py"}
    assert files["new.txt"].status == "added"
    assert files["old.py"].status == "deleted"
    assert files["logo.png"].is_binary
    assert files["b.py"].status == "renamed"
    assert files["b.py"].old_path == "a.py"


def test_commentable_lines_are_exact():
    util = {f.path: f for f in parse_unified_diff(SAMPLE)}["app/util.py"]
    # first hunk new side: 1 import os, 2 import sys(+), 3 blank, 4 def f, 5 return 2(+)
    # second hunk new side starts at 21
    assert util.commentable_lines == frozenset({1, 2, 3, 4, 5, 21, 22, 23, 24})
    assert util.added_line_count == 3
    assert util.removed_line_count == 1


def test_no_newline_marker_is_ignored():
    new = {f.path: f for f in parse_unified_diff(SAMPLE)}["new.txt"]
    assert [line.text for line in new.hunks[0].lines] == ["hello", "world"]
    assert new.commentable_lines == frozenset({1, 2})


def test_hunk_old_range_and_render():
    util = {f.path: f for f in parse_unified_diff(SAMPLE)}["app/util.py"]
    assert util.hunks[0].old_range == (1, 4)
    rendered = util.hunks[0].render()
    assert rendered.startswith("@@ -1,4 +1,5 @@")
    assert "+import sys" in rendered
    assert "-    return 1" in rendered


def test_empty_diff():
    assert parse_unified_diff("") == []

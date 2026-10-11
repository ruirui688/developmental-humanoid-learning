# First revision AST checker failure

The first inline revision-source checker failed before writing its report:

```text
Traceback (most recent call last):
  File "<stdin>", line 31, in <module>
AttributeError: 'Assign' object has no attribute 'body'
```

The harness indexed `run_diagnostic.body[-2].body`; that item is an Assign,
not the function's Try block. This was a check-harness failure. F source was
not changed because of it. The replacement selects the actual `ast.Try` node
and retains its outcome in `AST_SOURCE_CHECK_02.json`.

First-attempt work: four local source/protocol reads, two AST parses, zero
body-model imports, statistical math, RLS, physics, E/C/D reads or Git calls.
It reached 17 direct protected-function comparisons and the normalized derive
comparison before the exception, but no successful-check count is claimed.
Source files did not change between the two attempts. The exact byte total is
therefore the same four-source read total retained in the second report.
No SHA256 call had executed in the failed inline harness (hashes were assembled
after the failed expression). Tool wrapper wall was .5386348s; CPU unavailable.

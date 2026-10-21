# Hand-written test fixture — NOT real data

`amlworld_hi_small_sample.csv` is **hand-written** by us to mimic the *published*
IBM AMLworld header format. It is **not** a sample of the real IBM dataset, it is
**not** real financial data, and it is **not** derived from it.

Its only purpose is to let `api/tests/test_amlworld_loader.py` exercise the loader
without requiring the multi-hundred-megabyte real file, which is never committed.

It deliberately reproduces the published quirks the loader must survive:

- a **duplicate `Account` header** (column 3 = sender, column 4 = receiver), which
  pandas renames to `Account.1`;
- the same account string (`8000A1`) used under different banks, to exercise the
  `(bank, account)` identity rule;
- a repeated `(sender, receiver)` pair, to exercise edge-label aggregation;
- a `Is Laundering` column with a mixture of 0 and 1.

No bank names, account numbers or amounts here correspond to anything real.

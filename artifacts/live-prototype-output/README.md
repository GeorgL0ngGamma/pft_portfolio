# Live Prototype Output

These files were downloaded from the successful `Live Prototype` GitHub Actions run for commit `9153d32e78200cb62c10aea0c9bee68dbe08844f`.

Workflow run: https://github.com/GeorgL0ngGamma/pft_portfolio/actions/runs/25080417883

The CSV files are generated public-data examples for reviewer convenience. Regenerate them with:

```bash
PYTHONPATH=src DATABASE_URL="postgresql://postgres:postgres@localhost:5432/pft_portfolio" \
  python3 examples/live_prototype.py --output-dir prototype-output
```

`summary.json` contains the row counts, quality counters, workflow metadata, and Postgres table counts from the run.

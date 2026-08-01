# k6-loadtest

K6-based SQL Server load tester with a Python preprocessor. Turns parquet (or synthetic data specs) into a K6 test bundle: CREATE TABLE DDL, chunked JSON payloads, a K6 `test.js`, and a manifest.

→ **[Full guide](../docs/guides/k6-loadtest.md)**

Migrated from [`taxi-seed`](https://github.com/andrekamman/taxi-seed) (removed there in
`2a8909f`): load testing consumes the taxi data rather than producing it, and it needs a
Go-built xk6 binary, which is a poor fit for a pip-installable seeder. The preprocessor
still imports `taxi_shared` from `taxi-seed`, which is why that is a dependency of this
repo.

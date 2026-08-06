# k6-loadtest

A K6 load tester for SQL Server, with a Python preprocessor in front of it. The
preprocessor reads parquet files (or a synthetic data spec) and writes a K6 test bundle:
`CREATE TABLE` DDL, chunked JSON payloads, a K6 `test.js`, and a bundle manifest.

→ **[Full guide](../docs/guides/k6-loadtest.md)**

## Why it lives here

This code came from [`taxi-seed`](https://github.com/andrekamman/taxi-seed), which removed
it in `2a8909f`. Two reasons for the move:

- Load testing consumes the taxi data. taxi-seed produces it. This repo holds the
  consumers.
- A load test needs an xk6 binary built with Go. taxi-seed is a pip-installable package,
  so a Go toolchain sits badly in it.

The preprocessor still imports `taxi_shared` from taxi-seed. That is why taxi-seed is a
dependency of taxi-lab.

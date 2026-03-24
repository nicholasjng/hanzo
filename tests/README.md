# Testing hanzō

The tests are grouped into two parts:

1) Example projects (`projects/` directory)
2) Unit tests for hanzō functionality (`unit/` directory)

The former is used to verify the correctness of hanzō's build backend both in terms of functionality (can extensions be built, can builds be customized) and in comparison with established build backends (are there unacceptable regressions against other build backends). The latter tests central functionality of hanzō code, especially the extensions facility.

## Running tests

Remember to first install all test dependencies by running `uv sync --group tests`.

To build a specific test project, run `python -m build tests/projects/$PROJECT`.
To run all unit tests, run `pytest tests/unit`.

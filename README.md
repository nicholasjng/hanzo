# hanzō: A small, extensible build backend for Python based on ninja

This project is designed as an exercise to learn more about Python packaging, specifically in the context of compiled extensions.
Its goal is to enable modern (PEPs 517/660) wheel builds with support for compiled extensions, while being as minimal as possible.

This is not production-ready software, use with caution.

## Requirements

The only hard requirement is Python 3.11+.
When building an extensions, both ninja and any tools used in its constituting build rules must also be installed.

## Installation

Using [uv](https://docs.astral.sh/uv/) is recommended for installation, as there is no PyPI release yet.
To install directly from the GitHub repository, add the project as a source in your `pyproject.toml`:

```toml
[tool.uv.sources]
hanzo = { git = "https://github.com/nicholasjng/hanzo" }
```

More information, for example on how to request a specific branch or tag, can be found in the uv sources [documentation](https://docs.astral.sh/uv/concepts/projects/dependencies/#git).

To install a local clone of hanzō, for example for development purposes, use a local path:

```toml
[tool.uv.sources]
hanzo = { path = "/path/to/hanzo", editable = true }
```

## Building with hanzō

As with every PEP517 build backend, configure the use of hanzō directly in your `pyproject.toml`:

```toml
# file: pyproject.toml
[build-system]
requires = ["hanzo"]
build-backend = "hanzo"
```

Documentation on how to build extensions with hanzō is TBD.

"""Tests for the character system.

Deliberately NOT named `tests/characters`: that shadows the runtime package
`characters` (apps/synthesus/runtime/packages/characters) as soon as this
directory becomes a package, and `from characters.archive import ...` then
resolves here instead. Every sibling test package has an `__init__.py`, so the
directory name is what had to change.
"""

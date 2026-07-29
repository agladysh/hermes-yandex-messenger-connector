"""Hermes platform-plugin entry point for Yandex Messenger."""

if __package__:
    from .adapter import register
else:  # Pytest/local source loading without a package parent.
    from adapter import register

__all__ = ["register"]

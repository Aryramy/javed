"""Test version metadata and package discovery."""

import javed
from javed.version import __version__


def test_version_string():
    """Verify package exposes a semantic version string."""
    assert isinstance(__version__, str)
    assert len(__version__.split(".")) >= 3
    assert javed.__version__ == __version__
    assert __version__ == "0.1.0"

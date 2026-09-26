# A package, so that pytest imports tiles/tests/conftest.py as
# `tests.conftest`: names/tests/conftest.py is a rootdir-less `conftest`
# module the names tests import helpers from, and a second plain `conftest`
# would replace it in sys.modules when both directories run together.

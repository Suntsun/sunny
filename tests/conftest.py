import pytest
from sunny.core.logging import logger as L
from sunny.core.prompts import loader


@pytest.fixture(autouse=True)
def _auto_reset():
    L._reset_logging()
    loader._reset_cache()
    yield
    L._reset_logging()
    loader._reset_cache()
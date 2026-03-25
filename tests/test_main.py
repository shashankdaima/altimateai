import sys
import os
# Not sure about this. 
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from main import add


def test_add():
    assert add(1, 2) == 3
    assert add(-1, 1) == 0
    assert add(0, 0) == 0
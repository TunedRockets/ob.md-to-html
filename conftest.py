
# fix importing issues
import sys
from pathlib import Path
directory = str(Path(__file__).parent.resolve()) # the main directory
sys.path.append(directory)

from src.parser import parse_md
import json
import pytest

def check(test_data):

    md:str = test_data['markdown']
    html:str = test_data['html']
    guess = parse_md(md)
    assert html.strip() == guess.strip()



def pytest_generate_tests(metafunc): # don't work...

    with open("test-data/spec.json") as file:
        spec = json.load(file)
    
    metafunc.parameterize('test_data',list(spec), indirect=True)
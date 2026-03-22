
# fix importing issues
import sys
from pathlib import Path
directory = str(Path(__file__).parent.resolve()) # the main directory
sys.path.append(directory)

from src.parser import parse_md
import json
from io import StringIO
import pytest


def load_data()->list[dict]:
    with open("test-data/spec.json", 'r', encoding="utf-8") as file:

        lines = file.readlines()
        spec = json.loads("".join(lines))
        # spec = json.load(file, encoding="utf-8", errors="ignore")
    return list(spec)


spec = load_data()

@pytest.mark.parametrize('specs', spec)
def test_check(specs):

    md = StringIO(specs['markdown'])
    html:str = specs['html']
    guess = parse_md(md) # 
    assert guess.strip() == html.strip()



if __name__ == "__main__":

    # test individual test:
    id = 7 # id in pytest is one less than this
    test_check(spec[id-1])

    

# fix importing issues
import sys
from pathlib import Path
directory = str(Path(__file__).parent.resolve()) # the main directory
sys.path.append(directory)

from src.parser import parse_md
import json
from io import StringIO
import pytest


def load_data(max:int=-1)->list[dict]:
    with open("test-data/spec.json", 'r', encoding="utf-8") as file:

        lines = file.readlines()
        spec = json.loads("".join(lines))
        # spec = json.load(file, encoding="utf-8", errors="ignore")
    return list(spec)[0:max]


spec = load_data()

@pytest.mark.parametrize('specs', spec)
def test_check(specs):

    md = StringIO(specs['markdown'])
    html:str = specs['html']
    guess = parse_md(md) # 
    assert guess.strip() == html.strip()



if __name__ == "__main__":

    # test individual test:
    id = 42
    test_check(spec[id])

# top number passed: 373 (more passed than failed!)
# < 11 is tab issues
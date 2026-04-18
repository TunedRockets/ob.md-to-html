
# fix importing issues
import sys
from pathlib import Path
directory = str(Path(__file__).parent.resolve()) # the main directory
sys.path.append(directory)

from src.parser import parse_md
import json
from io import StringIO
import pytest

EXCLUDED = [608, 611, 612, 1624]

def load_data(max:int=-1)->list[dict]:
    with open("test-data/spec.json", 'r', encoding="utf-8") as file:

        lines = file.readlines()
        spec = json.loads("".join(lines))
    return list(spec)[0:max]


spec = load_data()

@pytest.mark.parametrize('specs', spec)
def test_check(specs):

    md = specs['markdown']
    html:str = specs['html'] # padd
    guess = parse_md(StringIO(md))
    test_id = specs['example']
    test_category = specs['section']
    if __name__ == "__main__":
        print(f'---#: {test_id} ------- {test_category} ------------------')
        print(md)
        print('-------------/\\Markdown/\\------------------------')
        print(guess)
        print("--------- /\\guess/\\ ----- \\/key\\/ ------------")
        print(html)
    elif int(test_id) in EXCLUDED: return;
    assert guess.strip() == html.strip()


if __name__ == "__main__":

    # test individual test:
    id = 682
    test_check(spec[id])


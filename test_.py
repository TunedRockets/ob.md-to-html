
# fix importing issues
import sys
from pathlib import Path
directory = str(Path(__file__).parent.resolve()) # the main directory
sys.path.append(directory)

from src.parser import parse_md
from src.utils import label_collapse
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



def test_wikilinks1():
    md = 'this is a [[wikilink]]\n'
    link = {
        "label":label_collapse('wikilink'),
        'dest': '/uri',
        'title': '',
        'wiki':True
    }
    link_refs = [link]
    html = '<p>this is a <a href="/uri">wikilink</a></p>'
    guess = parse_md(StringIO(md), link_references=link_refs)
    assert guess.strip() == html.strip()

def test_wikilinks2():
    md = 'wikilinks can target headings as well [[page#start]], but doesn\'t check validity\n'
    link = {
        "label":label_collapse('page'),
        'dest': '/uri',
        'title': '',
        'wiki':True
    }
    link_refs = [link]
    html = '<p>wikilinks can target headings as well <a href="/uri#start">page#start</a>, but doesn\'t check validity</p>'
    guess = parse_md(StringIO(md), link_references=link_refs)
    assert guess.strip() == html.strip()

def test_wikilinks3():
    md = 'even to headings inside the page [[#end]], which needs no link reference\n'

    html = '<p>even to headings inside the page <a href="#end">end</a>, which needs no link reference</p>'
    guess = parse_md(StringIO(md))
    assert guess.strip() == html.strip()

def test_wikilinks4():
    md = 'finally wikilinks can have [[wikilink|alternate names]]\n'
    link = {
        "label":label_collapse('wikilink'),
        'dest': '/uri',
        'title': '',
        'wiki':True
    }
    link_refs = [link]
    html = '<p>finally wikilinks can have <a href="/uri">alternate names</a></p>'
    guess = parse_md(StringIO(md), link_references=link_refs)
    assert guess.strip() == html.strip()


if __name__ == "__main__":

    # test individual test:
    id = 656
    test_check(spec[id])


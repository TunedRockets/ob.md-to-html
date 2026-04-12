'''
utilities, not required to be in the main file
'''
import re
import unicodedata as uni
from pathlib import Path
import json
with open(Path(__file__).parent.joinpath("entities.json")) as file:
    HTML_ENTITIES:dict = json.load(file)


# huge regex for tag

HTML_WHITE = r'(([ \t]+\n?[ \t]*)|([ \t]*\n?[ \t]+)|(\n))' # space, tab and up to one line ending (at least one)
# A tag name consists of an ASCII letter followed by zero or more ASCII letters, digits, or hyphens (-).
HTML_TAG_NAME = r'([a-zA-Z][a-zA-Z0-9-]*)'
# An attribute name consists of an ASCII letter, _, or :, followed by zero or more ASCII letters, digits, _, ., :, or -.
HTML_ATTR_NAME = r'([a-zA-Z_:][a-zA-Z0-9_\.:-]*)'
# An unquoted attribute value is a nonempty string of characters not including spaces, tabs, line endings, ", ', =, <, >, or `.
HTML_UNQUOT_VAL = r'([^ \t\n"\'=<>`]+)'
# A single-quoted attribute value consists of ', zero or more characters not including ', and a final '.
HTML_ONEQUOT_VAL = r"('[^']*')"
# A double-quoted attribute value consists of ", zero or more characters not including ", and a final ".
HTML_TWOQUOT_VAL = r'("[^"]*")'
# An attribute value consists of an unquoted attribute value, a single-quoted attribute value, or a double-quoted attribute value.
HTML_ATTR_VAL = f'({HTML_UNQUOT_VAL}|{HTML_ONEQUOT_VAL}|{HTML_TWOQUOT_VAL})'
# An attribute value specification consists of optional spaces, tabs, and up to one line ending, 
# a = character, optional spaces, tabs, and up to one line ending, and an attribute value.
HTML_ATTR_VAL_SPEC = f'({HTML_WHITE}?={HTML_WHITE}?{HTML_ATTR_VAL})'
# An attribute consists of spaces, tabs, and up to one line ending, an attribute name, and an optional attribute value specification.
HTML_ATTR = f'({HTML_WHITE}{HTML_ATTR_NAME}{HTML_ATTR_VAL_SPEC}?)'

# An open tag consists of a < character, a tag name, zero or more attributes, 
# optional spaces, tabs, and up to one line ending, an optional / character, and a > character.
HTML_OPEN_TAG = f'^<{HTML_TAG_NAME}{HTML_ATTR}*{HTML_WHITE}?/?>$'

# A closing tag consists of the string </, a tag name, optional spaces, 
# tabs, and up to one line ending, and the character >.
HTML_CLOSING_TAG = f'^</{HTML_TAG_NAME}{HTML_WHITE}?>$'


def is_HTML_tag(tag:str)->bool:
    '''checks if tag is a valid HTML tag'''
    if re.match(HTML_OPEN_TAG, tag): return True
    elif re.match(HTML_CLOSING_TAG, tag): return True
    else: return False


ATTRIBUTE_START = r"[a-zA-Z_.:-]+"
ATTRIBUTE_PATTERN = r"[a-zA-Z_:]"
UVALUE_SET = ('"', "'", '=', '<', '>', '`')
def is_HTML_tag_old(tag:str)->bool:
    '''checks if a tag (with opening brackets) is a valid html tag.
    more properly, it checks that:
    - line begins with `<` or `</`
    - followed by a tag-name
    - followed by 0 or more attributes, with optional attribute values
    - followed by `>`
    - each separated by spaces, tabs, and up to one line ending'''

    
    # ensure tags are in place:
    if not (tag[0]=='<' and tag[-1] == '>'): return False

    # strip end tag:
    tag = tag.rstrip('>')
    if tag[-1] == '/' and tag[-2] in (' ', '\t', '\n'):
        tag = tag[:-1]

    # start with line beginning:
    sp = tag.split()
    name = sp[0]
    if name[0] != '<': return False
    if len(name) < 2: return False
    if name[1] == '/':
        # closing tag, that's easy
        # just check that name is valid name

        if is_HTML_tag_name(name[2:]):
            return True
        else:
            return False
    # else:
    #check valid name:
    if not is_HTML_tag_name(name[1:].rstrip('>').rstrip('/')): return False

    # now go through and make sure attributes are valid:
    l = "".join(sp[1:]).lstrip() # currently not checking newline amount

    # stripping end:
    l = l.strip('>').strip('/')

    mode_in = 's' # 's': start 'a' : attribute name, 'u' : unquoted, '"' : single quoted, ''' double quoted
    eat = True
    for c in l:
        if eat:
            if c in (' ', '\t', '\n'): continue
            else: eat = False # stop eating
        match mode_in:
            case 's': # start
                if not re.fullmatch(ATTRIBUTE_START, c): return False # invalid start
                mode_in = 'a'
            
            case 'a': # inside attribute name
                if c in ('\n',' ', '\t'):
                    eat = True
                    mode_in = '='
                    continue
                elif c == '=':
                    eat = True
                    mode_in = 'r'
                    continue
                else:
                    if not re.fullmatch(ATTRIBUTE_START, c): return False # invalid start
                    continue
            case '=': # looking for equals or new attribute
                if c != '=': # new attribute
                    if not re.fullmatch(ATTRIBUTE_START, c): return False # invalid start
                    mode_in = 'a'
                else:
                    eat = True 
                    mode_in = 'r'
                    continue
            case 'r': # looking to start value
                if c == '"':
                    mode_in = '"'
                    continue
                elif c == "'":
                    mode_in = "'"
                    continue
                elif c in UVALUE_SET: return False # invalid start
                else:
                    mode_in = 'u'
                    continue
            case '"': # continue until other quote, anything goes
                if c == '"':
                    eat=True
                    mode_in = 's'
                continue
            case "'": # continue until other quote, anything goes
                if c == "'":
                    eat=True
                    mode_in = 's'
                continue
            case 'u': # continue until space or invalid
                if c in UVALUE_SET: return False
                elif c in ('\n',' ', '\t'):
                    eat = True
                    mode_in = 's'
    # if you made it through all that, you're a valid tag
    return True           

NAME_START = r"[a-zA-Z]"
NAME_PATTERN = r"[a-zA-Z0-9-]+"
def is_HTML_tag_name(name:str)->bool:
    '''checks if string is valid HTML tag-name'''
    if not re.fullmatch(NAME_PATTERN, name): return False
    if not re.fullmatch(NAME_START, name[0]): return False
    return True

URI_VALID = '[a-zA-Z0-9!#$&\'()*+,/:;=?@._~-]' # HTML sanitizing takes priority, so those are allowed through
# trial and error on which reserved characters are allowed...
def URI_sanitize(link:str):
    '''superset of HTML sanitize that also replaces non-allowed characters with % replacements,
    any already existing % are kept'''
    out = []
    for idx, c in enumerate(link):
        if re.fullmatch(URI_VALID,c): out.append(replace_danger(c))
        elif c == '%' and len(link)>idx+2:
            # might be existing code, keep if followed by at least 2 digits
            if re.match('[0-9]{2}',link[idx+1]+link[idx+2]): out.append('%')
        else:
            # split up in UTF-8 bytes, each byte encoded in hex after a percent
            for b in c.encode():
                out.append(f'%{b:X}')
    return "".join(out)


HTML_REF_WORD = r'(^|[^\\])(\\\\)*(&[a-zA-Z0-9]+;)' # TODO: ensure '([^\\]|^)' works 
HTML_REF_DIGIT = r'(^|[^\\])(\\\\)*(&#[Xx]?[a-fA-F0-9]{1,7};)'
ASCII_PUNCTUATION_ESCAPE = r'\\[!"#$%&\'()*+,-./:;<=>?@\[\\\]\^_`{|}~]'
HTML_Danger = {'"': "&quot;", '&': "&amp;", '<': "&lt;", '>': "&gt;", '\u0000' : '\uFFFD'}
def sanitize_text(s:str, escape:bool=True, resolve_refs:bool=True, replace_dangerous:bool=True)->str:
    '''General sanitization function that, depending on provided options:
    - Replaces escaped characters with their literal counterpart
    - resolves HTML character references
    - replaces HTML breaking characters with their reference counterpart.
    Specifically it does this so they play along, not stepping on each other's toes'''


    if resolve_refs:
        # difficult because findall doesn't allow overlap
        donor = s
        while not (m:=re.search(HTML_REF_WORD, donor)) is None:
            mg = m.groups('') # make the empty ones '' not None
            tgt = m[0]
            if mg[2] in HTML_ENTITIES.keys():
                val = mg[0] + mg[1] + HTML_ENTITIES[mg[2]]['characters']
                s = s.replace(tgt,val,1)
            donor = donor[m.end():] # remove from consideration

        while not (m:=re.search(HTML_REF_DIGIT, donor)) is None:
            try:
                tgt = m[0]
                mg = m.groups('') # make the empty ones '' not None
                i = int(mg[2][3:-1],16) if mg[2][2] in ('X','x') else int(mg[2][2:-1])
                val = mg[0] + mg[1] + chr(i) # TODO: does not repace invalid characters with \uFFFD
                s = s.replace(tgt,val,1) # keep ignored backslashes
            except ValueError: pass # for the case of gibberish hex-dec
            donor = donor[m.end():] # remove from consideration
        # NOTE: might technically break if the same code is escaped several times 
        # in the same line, but with different number of escapes
        # so replace with positioning based on index instead of replace()?
    if escape:
        while (m:= re.search(ASCII_PUNCTUATION_ESCAPE, s)):
                s = s.replace(m[0],m[0][1])
    if replace_dangerous: # might be a better way but this works
        s = replace_danger(s)

    return s

def replace_danger(s:str)->str:
    '''replaces dangerous HTML characters with safe counterparts'''
    o = []
    for c in s:
        if c in HTML_Danger.keys(): o.append(HTML_Danger[c])
        else: o.append(c)
    return "".join(o)

SCHEME_PATTERN = r'[a-zA-Z+.-]{2,32}'
URI_NOMATCH = r'[\u0000-\u001F\u007f <>]'
def valid_URI_link(link:str):
    '''checks if link is valid URI link.
    links consist of a scheme, which is a sequence of 2-32 chars
    starting with ASCII letter and followed by ASCII,digits, or `+`, `.`, or `-`
    followed by a colon `:`, followed by zero or more characters, not including ASCII control
    characters, space, `<` or `>`'''
    scheme,colon,rest = link.partition(':')
    if colon == '': return False # no colon
    if not re.fullmatch(SCHEME_PATTERN, scheme): return False
    if re.match(URI_NOMATCH,rest): return False
    return True

def valid_destination_link(link:str, allow_incomplete:bool=True):
    '''link destinations can be broader than URI links, so have less strict rules.
    Can either be bracketed in `<>`, or not, in which case no control characters, or space is allowed,
    and no unbalanced non-backspaced parentheses'''

    if link[0] == '<':
        # bracketed
        if allow_incomplete:
            link = link.rstrip('>')
        elif link[-1] != '>': return False

        # look for unescaped brackets
        if re.search(r'\w*[\[\]](?<!\\)', link[1:]): return False # not sure on the regex
        else: return True
    # else:
    count = 0
    for c in link:
        if ord(c) <= 0x1F or c in ('\u007F', ' '): return False
        # check for balanced parentheses:
        if c == '(': count += 1
        elif c == ')': count -=1
        if count < 0: return False
    return True

EMAIL_SPEC = r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
def valid_email(email:str):
    '''valid email is anything that matches the "non-normative regex from the HTML5 spec"'''
    if re.fullmatch(EMAIL_SPEC,email): return True
    else: return False

UNESCAPED_START = r'(^|[^\\])(\\\\)*'
def valid_link_title(title:str)->bool:
    '''checks if link title, including enclosing characters, is valid'''
    if title == '': return True
    if title[0] == '"' and title[-1] == '"':
        if re.search(UNESCAPED_START + r'"',title[1:-1]): return False
        else: return True

    elif title[0] == "'" and title[-1] == "'":
        if re.search(UNESCAPED_START + r"'",title[1:-1]): return False
        else: return True

    elif title[0] == '(' and title[-1] == ')':
        if re.search(UNESCAPED_START + r')',title[1:-1]): return False
        else: return True
    else: return False



UNESCAPED_PAR = UNESCAPED_START + r'\)'
UNESCAPED_ANG_BRACE = UNESCAPED_START + r'>'
UNESCAPED_BRACE = UNESCAPED_START + r']'
UNESCAPED_BRACES = UNESCAPED_START + r'[\[\]]'
def valid_label_name(name:str):
    '''checks if label name is valid, bust have at least one non-whitespace character
    and must not have any unescaped `]`, and a max of 999 chars long, name assumed to be sanitized of opening and closing brackets'''
    if len(name) > 999: return False
    if len(name.strip()) == 0: return False
    if re.search(UNESCAPED_BRACES, name): return False # looking for unescaped `]` or `[`
    return True

def label_collapse(label:str)->str:
    '''perform operations to collapse label in reference links'''

    label = label.casefold().strip().replace('\t',' ').replace('\n',' ')
    label = " ".join(label.split())
    return label

def lstrip2(s:str, c:str,i:int)->str:
    '''lstrip but with a limit on how many'''
    for _ in range(i):
        if s[0] == c: s = s[1:]
        else: break
    return s

def tab_shuffle(s:str)->str:
    '''Shuffles leading tabs so that spaces go to the inside.
    needed because of the strange pseudotab behaviour'''
    if (ind := re.match(r'[ \t]+',s)) is None: return s # no need to do anything
    # fix ind:
    ind = ind[0]
    while '  \t' in ind:
        ind = ind.replace('  \t', '\t  ') # shuffle tabs
    return ind + s[len(ind):]


if __name__ == "__main__":
    teststr = 'f&ouml;&ouml;&lt;'
    print(sanitize_text(teststr))

    
        
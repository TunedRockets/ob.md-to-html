'''
utilities, not required to be in the main file
'''
import re


ASCII_PUNCTUATION_ESCAPE = r'\\[!"#$%&\'()*+,-./:;<=>?@\[\\\]\^_`{|}~]'

ATTRIBUTE_START = r"[a-zA-Z_.:-]+"
ATTRIBUTE_PATTERN = r"[a-zA-Z_:]"
UVALUE_SET = ('"', "'", '=', '<', '>', '`')
def is_HTML_tag(tag:str)->bool:
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
    sp = tag.split(' ')
    name = sp[0]
    if name[0] != '<': return False
    if len(name) < 2: return False
    if name[1] == '/':
        # closing tag, that's easy
        if tag.rstrip()[-1] != '>': return False
        # otherwise just check that name is valid name

        if is_HTML_tag_name(name[2:].rstrip('>')):
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
    '''superset of HTML sanitize that also replaces non-allowed characters with % replacements'''
    out = []
    for c in link:
        if re.fullmatch(URI_VALID,c): out.append(HTML_sanitize(c))
        else:
            out.append(f'%{ord(c):X}')
    return "".join(out)

HTML_replace = {'"': "&quot;", '&': "&amp;", '<': "&lt;", '>': "&gt;", '\u0000' : '\uFFFD'}
def HTML_sanitize(string:str)->str:
    '''returns a sanitized version of the string as to not use symbols
    that might break HTML formatting'''
    
    
    # oneliner for one-lengths
    if len(string) == 1: return HTML_replace[string] if string in HTML_replace.keys() else string
    
    out = []
    for c in string:
        if c in HTML_replace.keys():
            out.append(HTML_replace[c])
        else: out.append(c)
    return "".join(out)

SCHEME_PATTERN = r'[a-zA-Z+.-]{2,32}'
URI_NOMATCH = r'[\u0000-\u001F\u007f <>]'
def valid_URI_link(link:str):
    '''checks if link is valid URI link.
    links consist of a scheme, which is a sequence of 2-32 chars
    starting with ASCII letter and followed by ASCII,digits, or `+`, `.`, or `-`
    followed by a colon `:`, followed by zero or more characters, not including ASCII control
    characters, space, `<` or `>`'''
    scheme,_,rest = link.partition(':')
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

def valid_link_title(title:str)->bool:
    '''checks if link title, including enclosing characters, is valid'''
    if title == '': return True
    if title[0] == '"' and title[-1] == '"':
        if re.search(r'\w*["](?<!\\)',title[1:-1]): return False
        else: return True

    elif title[0] == "'" and title[-1] == "'":
        if re.search(r"\w*['](?<!\\)",title[1:-1]): return False
        else: return True

    elif title[0] == '(' and title[-1] == ')':
        if re.search(r'\w*[()](?<!\\)',title[1:-1]): return False
        else: return True
    else: return False

EMAIL_SPEC = r"/^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/"
def valid_email(email:str):
    '''valid email is anything that matches the "non-normative regex from the HTML5 spec"'''
    if re.fullmatch(EMAIL_SPEC,email): return True
    else: return False

def valid_label_name(name:str):
    '''checks if label name is valid, bust have at least one non-whitespace character
    and must not have any unescaped `]`, and a max of 999 chars long, name assumed to be sanitized of opening and closing brackets'''
    if len(name) > 999: return False
    if len(name.strip()) == 0: return False
    if re.search(r'\w*\](?<!\\)', name): return False # looking for unescaped `]`
    return True

def label_collapse(label:str)->str:
    '''perform operations to collapse label in reference links'''

    label = label.casefold().strip().replace('\t',' ').replace('\n',' ')
    label = " ".join(label.split())
    return label

if __name__ == "__main__":
    teststr = r'bla\* foo\%, zap \@'

    while m := re.search(ASCII_PUNCTUATION_ESCAPE,teststr):
        print(teststr[m.start():m.end()])
        
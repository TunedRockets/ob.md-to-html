'''
separate part for inline functions
'''
import unicodedata as uni
from pathlib import Path
import sys
directory = str(Path(__file__).parent.resolve()) # the src directory
sys.path.append(directory)
from utils import *
import json
with open(Path(__file__).parent.joinpath("entities.json")) as file:
    HTML_ENTITIES:dict = json.load(file)



delimeter_stack = []
def inline_parse(text:str, link_references)->str:
    '''runs the inline parse on the text, in order to (in order of precedence):
    - insert code spans
    - insert emphasis
    - insert links
    - insert autolinks
    - pass through raw HTML
    - format line breaks
    - escape characters
    - convert HTML codes to unicode
    - replace dangerous characters with HTML codes

    Version 2
    '''
    global delimeter_stack
    delimeter_stack = [] # reset stack

    out = [""] # improvement over v1, out is a list of strings
    # better this than a linked list and allows some pointer-like things
    stream = fakestream(text.lstrip())
    
    while (c := stream.read(1)) != '':
        
        if (t := parse_inline_code(stream,c)):
            out.extend([t, '']) # type:ignore
            continue
        
        if (t := parse_inline_emphasis(stream,out,c)):
            out.extend([t, '']) # type:ignore
            continue
        
        

        if (t := parse_inline_links(stream,out,c, link_references)):
            if isinstance(t, list): out = t
            else: out.extend([t, '']) # type:ignore
            continue

        if (t := parse_inline_HTML(stream,c)):
            out.extend([t, '']) # type:ignore
            continue

        if (t := parse_inline_autolink(stream, c)):
            out.extend([t,'']) #type:ignore
            continue

        if (t := parse_inline_escape(stream,c)):
            out[-1] += t # type:ignore
            continue

        if parse_inline_linebreak(stream, out,c):
            continue

        if (t := parse_inline_char_ref(stream,c)):
            out[-1] += t # type:ignore
            continue
        
        # else:
        out[-1] += replace_danger(c) # check for danger

    process_emphasis(out, -1)
    # remove end breaks:
    if out[-1][-7:] == "<br />\n": out[-1] = out[-1][:-7]
    # strip end spaces:
    out[-1] = out[-1].rstrip()

    return ''.join(out)

class fakestream:
    '''stream-like interface for a string, to enable character by character parsing'''

    def __init__(self, content) -> None:
        self.content=content
        self.idx = 0
    
    def read(self, size):
        '''reads 'size' items out of the content'''
        try:
            if size == 1:
                self.idx += 1
                return self.content[self.idx-1]
            self.idx += size
            return self.content[(self.idx-size): (min(self.idx, len(self.content)))]
        except IndexError:
            self.idx
            return ''
    
    def move(self,pos):
        '''moves index by given amount'''
        self.idx += pos

def eat_until(stream:fakestream, stop:str)->str:
    '''Will read from the stream until the specified string is reached
    then return everything up to and including the string.
    if string not found, will move back read to start'''
    buf = stream.read(len(stop))
    while buf[-len(stop):] != stop:
        if (c := stream.read(1)) != '':
            buf += c
        else:
            # reached eof, go back
            stream.move(-len(buf)-2)
            return ''
    return buf

def parse_inline_code(stream:fakestream, c:str)->str|bool:
    '''read character, and if it's inline code, returns the resulting string.
    else returns false and backs up stream'''
    if c != '`': return False

    # count length of ticks:
    n = char_counter(stream, '`') + 1
    # found ticks, read into buffer until similar length found:
    buf = []
    while (d := stream.read(1)) != '':
        if d != '`':
            # just insert regular characters (except make newlines to space)
            # and sanitize it as html
            buf.append(d if d != '\n' else ' ')
            continue
        # else:
        m = char_counter(stream, '`') + 1 # number of ticks
        if m == n:
            # was matching, return buffer and tags
            out = ''.join(buf)

            # do space stripping rule.
            if out[0] == ' ' and out[-1] == ' ' and out.replace(' ','') != '':
                out = out[1:-1]

            return '<code>' + replace_danger(out) + '</code>'
        else:
            # just treat tags literally:
            buf.extend(['`']*m)
            continue
    # reached EOF, back up and ticks as literal:
    if d == '': stream.move(-1) # special case hit EOF
    stream.move(-len(buf))
    return '`' * n

def parse_inline_HTML(stream:fakestream, c:str)->str|bool:
    '''read character, and if it's inline HTML, returns the resulting string.
    else returns falseand backs up stream'''
    if c != '<': return False

    # check ahead if special tag:
    bite = stream.read(8)
    if bite[0:4] == '!---': # closed comment
        stream.move(-len(bite)+5)
        return '<!--->'
    elif bite[0:4] == '!-->': # closed comment #2
        stream.move(-len(bite)+4)
        return '<!-->'
    elif bite[0:3] == '!--': # comment
        stream.move(-len(bite)+3)
        return '<!--' + eat_until(stream, '-->')
    elif bite[0] == '?': # processing instruction
        stream.move(-len(bite)+1)
        return '<?' + eat_until(stream, '?>')
    elif bite == '![CDATA[': # CDATA
        return '<![CDATA[' + eat_until(stream, ']]>')
    elif bite[0] == '!': # Declaration
        stream.move(-len(bite)+1)
        return '<!' + eat_until(stream, '>')
    else:
        stream.move(-8) # move back

    # regular tags:
    buf = ''
    while (c2 := stream.read(1)) != '>':
        buf += c2
        if c2 == '':
            # reached EOF, so that's a false
            stream.move(-len(buf))
            return False

    if is_HTML_tag('<' + buf + '>'):
        return '<' + buf + '>'
    else:
        stream.move(-len(buf)-1)
        return False


def parse_inline_autolink(stream:fakestream, c:str):
    '''autolinks are links within `<>` brackets.
    .
    link formed as a normal HTML link with a title being the link
    (contents are HTML sanitized)
    
    the link may also be an email link, in which case an email link should be used.
    
    No spaces allowed inside'''
    if c != '<': return False

    link = eat_until(stream,'>')
    if link == '': # Hit EOF, invalid
        return False
    link = link[:-1] # strip `>`
    # else check for valid link or email:
    if valid_URI_link(link):
        return f'<a href="{URI_sanitize(link)}">{replace_danger(link)}</a>'
    elif valid_email(link):
        return f'<a href="mailto:{replace_danger(link)}">{replace_danger(link)}</a>'
    else: 
        stream.move(-len(link)-1) # for the strip
        return False
    
def parse_inline_linebreak(stream:fakestream, out:list[str], c:str)->bool:
    '''reads linbreak, and if it is figures out if it's soft or hard,
    then cleans out appropriately'''
    if c != '\n': return False


    # two+ spaces (or backslash, which is handles in escapes) hard break
    # else soft break
    if (len(out[-1])>=2 and out[-1][-2:] == '  ') or (len(out[-1])>=1 and out[-1][-1] == '\t'):
        # hard:
        # if we're at EOF then no hard break:
        if stream.read(1) == '':
            return True # end treatment will strip spaces
        else:
            stream.move(-1) # move back
            out[-1] = out[-1].rstrip() + '<br />\n'
    else:
        # soft break:
        out[-1] = out[-1].rstrip() + '\n'
        
    # get rid of next spaces:
    while (c := stream.read(1)) == ' ': pass
    stream.move(-1) # move back to read new line
    return True

def parse_inline_escape(stream:fakestream, c:str)->str|bool:
    '''reads for escape sequences if found, returns literal character.
    also deals with dangerous HTML characters'''
    if c != '\\': return False
    c = stream.read(1) # get potential escaping character
    if not c in ('!', '"', '#', '$', '%', '&', "'", '(', ')', '*', '+', ',', '-', '.', '/', ':', ';', '<', '=', '>', '?', '@', '[', '\\', ']', '^', '_', '`', '{', '|', '}', '~', '\n'):
        # not valid escape, treat as literal
        # since it can't be beginning something special just pass on literal:
        return '\\' + c
    # else:
    if c == '\n':
        # special case, back up and add two spaces for the inline break

        # except if at EOF, in which case keep the `\`:
        if stream.read(1) == '':
            return '\\'
        else:
            stream.move(-2) # for both forward reads
            return '  '
    else:
        return replace_danger(c)
    
def parse_inline_char_ref(stream:fakestream, c:str):
    '''checks if the following is a valid HTML character unicode referece.
    if yes returns the unicode character, else move back stream
    and return false.
    
    Uses the sanitize from the utils module'''
    if c != '&': return False
    # grab until semicolon:
    buf = [c]
    while (c1 := stream.read(1)) != ';':
        buf.append(c1)
        if c1 == '':
            # reached EOF, it's invalid so back up
            stream.move(-len(buf)+1)
            return False
    txt = ''.join(buf) + ';'
    
    
    if re.match(HTML_REF_WORD, ' '+txt) or re.match(HTML_REF_DIGIT, ' '+txt):
        return sanitize_text(txt,True,True,True) # will resolve the value
    # else:
    stream.move(-len(buf))
    return False



def parse_inline_emphasis(stream:fakestream, out:list[str], c:str)->str|bool:
    '''read character, if it starts emphasis, return an emphasis string
    and add to delimiter stack'''
    global delimeter_stack

    
    if not c in ('*','_'): return False

    # count:
    n = char_counter(stream, c) + 1

    # figure direction
    # left and/or right? (neither and it's just literal)
    d = 0
    lor = False
    fol = stream.read(1)
    stream.move(-1) # go back to not miss
    pre = out[-1][-1] if len(out[-1]) != 0 else ''
    # unicode category (since uni doesn't like none inputs):
    fol_c = uni.category(fol) if not fol == '' else '  '
    pre_c = uni.category(pre) if not pre == '' else '  '

    # check wether following and previous are punctuation or whitespace:
    fol_w = (fol_c == 'Zs' or fol in ('\u0009','\u000A','\u000C','\u000D', ''))
    pre_w = (pre_c == 'Zs' or pre in ('\u0009','\u000A','\u000C','\u000D', ''))
    fol_p = (fol_c[0] in ('P','S'))
    pre_p = (pre_c[0] in ('P','S'))

    # left (opener):
    if (not fol_w) and ((not fol_p) or (pre_w or pre_p)):
        d -= 1
        lor = True
    #right (closer):
    if (not pre_w) and ((not pre_p) or (fol_w or fol_p)):
        d +=1
        lor = True

    # special `_` check:
    if c == '_' and lor and d == 0:
        # if it is potentially both, extra conditions apply:
        # for left, need punctuation before,
        # for right, need punctuation after.
        if pre_p and fol_p:
            pass # d remains 0 can both open and close
        elif fol_p:
            d = 1 # not open, can close
        elif pre_p:
            d = -1 # not close, can open
        else:
            lor = False # can't open or close, just literal



    if lor: # add to stack
        delimeter_stack.append({
            "type": c,
            "length": n,
            "active": True,
            "dir": d,
            "idx": len(out) # place in out where it is
        })

    # return the raw string:
    return c * n


def parse_inline_links(stream:fakestream,out:list[str], c:str, link_references)->str|bool|list[str]:
    '''read character, if it starts link, return a link string
    and add to delimiter stack, if it ends link make link'''
    if not c in ('[','!', ']'): return False
    # this one's a doosey
    global delimeter_stack

    
    # check for `![`:
    if stream.read(1) == '[' and c == '!':
        c = '!['
        
    else:
        stream.move(-1)
    
    if c in ('[', '!['):
        # start of link
        delimeter_stack.append({
            "type": c,
            'active':True,
            "dir": 0, # irrelevant for links
            "length":0, # ---||---
            "idx": len(out) # place in out where it is
        })
        return c
    # else, close the link
    for delim in delimeter_stack[::-1]:
        if delim['type'] not in ('[', '!['): continue
        # found one!
        if not delim['active']:
            # inactive, remove and insert literal
            delimeter_stack.remove(delim)
            return c
        # now we get to the complicated stuff!
        

        link_content = "".join(out[delim['idx']:])[len(delim['type']):]

        # check if inline, reference, collapsed, or shortcut
        buf = [stream.read(1)]
        may_invalid = False
        match buf[0]:

            case '[':
                # ref or collapsed
                buf.append(stream.read(1))
                if buf[1] == ']': # collapsed
                    label = link_content
                    content = link_content
                    title = '' # let label fill out
                    dest = ''
                else:
                    # ref, read in label
                    while (c:=stream.read(1)) != ']':
                        if c == '':
                            # reached EOF, invalid link
                            stream.move(-len(buf))
                            delimeter_stack.remove(delim)
                            return ']'
                            
                        buf.append(c)
                        if c == '\\': buf.append(stream.read(1)) # disregard next from criteria
                    label = "".join(buf[1:])
                    buf.append(']') # so everything we read is in a buffer
                    content = link_content
                    title = ''
                    dest = ''
            case '(':
                # inline, next part is optional link destination and optional link title, followed by `)`
                label = ''
                content = link_content
                # bracketed destination?
                buf.append(stream.read(1))
                count = 0 # needed for later
                if buf[1] == '<':
                    # bracketed destination
                    # read until non-backspaced `>`
                    while (c := stream.read(1)) != '>':
                        buf.append(c)
                        if c == '\\': buf.append(stream.read(1))
                        if c == '':
                            # EOF, invalid
                            stream.move(-len(buf))
                            delimeter_stack.remove(delim)
                            return ']'
                    buf.append(c) # put everything read in buffer
                    # end of dest:
                    dest = "".join(buf[2:-1])
                else: # unbracketed, count parentheses
                    # edge case with empty link:
                    if buf[1] == ')':
                        dest = ''
                        count = -1
                        c = ')'
                    else:
                        while True:
                            c = stream.read(1)
                            buf.append(c)
                            if ord(c) <= 0x1F or c in ('\u007F', ' '):break
                            if c == '(': count += 1
                            elif c == ')': count -=1
                            if count < 0: # end parenthesis
                                break
                        dest = ''.join(buf[1:-1])
                # now it's title time, eat whitespace first (if count not negative):
                if count >= 0:
                    while (c:=stream.read(1)).strip() == '':
                        if c == '': break # EOF
                        buf.append(c)
                    buf.append(c) # first part of ev. title
                if c != ')': # check for title
                    tit_start = len(buf) 
                    match c:
                        case '"': end = '"'
                        case "'": end = "'"
                        case '(': end = ')'
                        case _:
                            # invalid!
                            stream.move(-len(buf))
                            delimeter_stack.remove(delim)
                            return ']'
                            pass
                    while (c := stream.read(1)) != end:
                        buf.append(c)
                        if c == '\\': buf.append(stream.read(1)) # ignore escaped chars
                        if c == '':
                            # EOF, invalid
                            stream.move(-len(buf))
                            delimeter_stack.remove(delim)
                            return ']'
                    buf.append(c)
                    title = ''.join(buf[tit_start:-1])  
                    # check for end parenthesis (and eat space):
                    while (c:= stream.read(1)).strip() == "": buf.append(c)
                    if c != ')':
                        # invalid!
                        stream.move(-len(buf)-1)
                        delimeter_stack.remove(delim)
                        return ']'
                else: # no title
                    title = ''
                
            case _:
                # shortcut or invalid
                stream.move(-1) # back up
                may_invalid = True
                label=link_content
                content = link_content
                title=""
                dest=""
        
        # fill in if label
        if label != '':
            for l in link_references:
                if label_collapse(label) == l['label']:
                    if l['title'] != '': title = l['title']
                    dest = l['dest']
                    break
            else:
                if may_invalid:
                    # invalid shortcut
                    stream.move(-len(buf)+1)
                    delimeter_stack.remove(delim)
                    return ']'

        # have valid, close out
        
        # check title and destination for escapes, and sanitize
        title = sanitize_text(title)
        dest = sanitize_text(dest)
        # more sanitizing for URI specifically:
        dest = URI_sanitize(dest)


        # add to out and clear it:
        out = out[:delim['idx']]
        image = (delim['type'] == '![')
        if image: # image
            out.append(f'<img src="{dest}"' + f' alt="{content}"'+ 
                (f' title="{title}"' if title != '' else '') + 
                ' />')
        else:
            out.append(f'<a href="{dest}"' + 
                (f' title="{title}"' if title != '' else '') + 
                f'>{content}</a>')

        # process emphasis on inside:
        delim_idx = delimeter_stack.index(delim)
        process_emphasis(out,delim_idx)

        # remove delimeter:
        delimeter_stack.remove(delim)

        # inactivate links if not image:
        if not image:
            for d in delimeter_stack[:delim_idx]:
                d['active'] = False

        return out # sign that we succeeded for inline parser


    else: # found none, insert literal:
        return c

def process_emphasis(out:list[str], stack_bottom:int = -1):
    '''Run process emphasis, until we reach indicated stack bottom'''
    curr_pos = stack_bottom+1
    openers_bottom = {'*' : stack_bottom, '_' : stack_bottom}
    global delimeter_stack

    while curr_pos < len(delimeter_stack):
        # get next closer:
        closer = delimeter_stack[curr_pos]
        if closer['dir'] < 0 or (not closer['type'] in ('*','_')):
            curr_pos += 1
            continue

        # look back for first matching, staying above bottom:
        for i in range(curr_pos- max(stack_bottom, openers_bottom[closer['type']])):
            opener = delimeter_stack[curr_pos-i] # potential opener
            if not (opener['type'] == closer['type'] and opener['dir']<=0 and opener != closer):
                continue # doesn't match
            # found valid one

            # three check:
            ''' "If one of the delimiters can both open and close emphasis, 
            then the sum of the lengths of the delimiter runs containing the opening 
            and closing delimiters must not be a multiple of 3 
            unless both lengths are multiples of 3." '''
            if opener['dir'] == 0 or closer['dir'] == 0:
                if opener['length'] % 3 == 0 and closer['length'] % 3 == 0:
                    pass # fine
                elif (opener['length'] + closer['length']) % 3 == 0:
                    # bad, no match
                    continue
                    


            is_strong = len(out[closer['idx']]) >=2 and len(out[opener['idx']]) >=2
            
            # add emphasis or strong to nodes between delimeters:
            if is_strong:
                out[opener['idx']+1] = '<strong>' + out[opener['idx']+1]
                out[closer['idx']-1] += '</strong>'

                # remove delimeters from delimeter run:
                closer['length'] -= 2
                out[closer['idx']] = closer['type']*closer['length']
                opener['length'] -= 2
                out[opener['idx']] = opener['type']*opener['length']
            else:
                out[opener['idx']+1] = '<em>' + out[opener['idx']+1]
                out[closer['idx']-1] += '</em>'

                # remove delimeters from delimeter run:
                closer['length'] -= 1
                out[closer['idx']] = closer['type']*closer['length']
                opener['length'] -= 1
                out[opener['idx']] = opener['type']*opener['length']

            # remove all delimiters between opener and closer:
            for j in range(curr_pos-1, curr_pos-i, -1):
                delimeter_stack.pop(j)
                curr_pos-=1 # to keep it accurate

            # remove delimeters if they're empty:
            if opener['length'] == 0:
                delimeter_stack.remove(opener)
                curr_pos -=1
            if closer['length'] == 0:
                delimeter_stack.remove(closer)
                # move to next, which automatically happens with curr_pos
            break
        else: # none found
            openers_bottom[closer['type']] = curr_pos -1 # lower bound in future
            if closer['dir'] != 0:
                # not opener either, remove it
                # (which advances curr_pos)
                delimeter_stack.remove(closer)
            else:
                curr_pos += 1

            continue

    # remove delimeters above stack bottom TODO
    delimeter_stack = delimeter_stack[:stack_bottom+1]
    return;

def char_counter(s:fakestream, c:str)->int:
    '''counts length of char run, and sets stream to end of run.'''
    tick_len = 0
    while s.read(1) == c:
        tick_len += 1
    s.move(-1) # go back one
    return tick_len

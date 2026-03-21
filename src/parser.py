
'''
Strategy:
in accordance with https://spec.commonmark.org/0.31.2/#appendix-a-parsing-strategy,
the parsing will work as follows:
1. first lines of input are consumed to construct the block structure
    parsing links but not any text
2. second the raw text is parsed into sequences.





Additional steps:
Aside from the patterms in commonmark, obsidian also uses:
- Tables
- task list items
- strikethrough
- autolinks
- disallowed raw HTML
from the GFM spec (https://github.github.com/gfm/), and the addition of:
- internal links
- embeded files
- block references (and defining a block)
- footnotes
- comments
- highlights
- callouts
that are additional extensions for obsidian (https://obsidian.md/help/obsidian-flavored-markdown)

there is also the LaTeX/KaTeX/MathJax blocks, which deserve attention
'''

from io import StringIO
import re
import unicodedata as uni

# grab HTML entities:
from pathlib import Path
import json
with open(Path(__file__).parent.joinpath("entities.json")) as file:
    HTML_entites:dict = json.load(file)

class Block():

    input:StringIO
    root:"Block"
    current_line:str
    reread_line:bool
    is_containter:bool = False # for block-quotes and lists
    parse_verbatim:bool = False # for code and HTML blocks

    def __init__(self,parent:"Block|None") -> None:
        self.contents:str = ""
        self.open:bool = True # blocks are open unless otherwise specified
        
        
        if not parent is None:

            # make sure parant can hold stuff (otherwise ask their parent)
            while not parent.is_containter: parent = parent.parent

            self.parent:"Block" = parent

            self.parent.children.append(self) # add child to parent
            self.parent.open_child = self # set onself as the open child
        else:
            # for the root:
            self.is_containter = True
        self.children:list["Block"] = []
        self.open_child:"Block|None" = None

    @staticmethod
    def init(input:StringIO):
        Block.root = Block(None)
        Block.input = input
        Block.reread_line = False
        

    @staticmethod
    def read_line()->bool:
        '''
        reads a new line from the input and updates the block tree.
        Procedure:
        1. Iterate through tree to find last (last child) open block
            check if line satisfies the block, if it does, add it, if not, 
            can't close just yet because of lazy continuation
        2. next, look for new block starts (e.g. '>'), if a new block starts,
            close all unmatched blocks from 1
        3. finally, what remains can be added to the content of the last open block
        '''

        if not Block.reread_line: # to deal with blocks that don't use the line
            Block.current_line = Block.input.readline()
        else: Block.reread_line = False # reset

        if Block.current_line == "": return False # EOF condition


        # get all open blocks, in descending order (can be improved)
        b = Block.root
        considered_blocks:list["Block"] = [b]
        while not (b := b.open_child) is None:
            considered_blocks.append(b)

        # check if block is matched (start looking from top down):
        block_matched = []
        for block in considered_blocks:
            block_matched.append(block.can_continue()) # removes continuation markers

        # at this point we can pretend to be at base level        

        # create new block if applicable ( and redo that if it was a containter):
        while (not (new_block := considered_blocks[-1].check_for_new_block()) is None):
            if not new_block.is_containter: break # leaf, end loop
            # else: add to list and go again
            considered_blocks.append(new_block)
        
        # some block eat the line without needing it added:
        if type(new_block) in (Thematic_break, Setext_heading):
            return True
        
        if not new_block is None:

            # close all not-prospective blocks:
            for i in range(len(block_matched)):
                if not block_matched[i]:
                    considered_blocks[i].open = False

            # add this block to consideration:
            considered_blocks.append(new_block)

        # now, find lowest open block and add contents to it:

        for b in considered_blocks[::-1]:
            if b.open:
                b.add_content(Block.current_line)
                return True

        return True # this should never be reached

    def add_content(self,content:str):
        '''adds content to block. if block that is a leaf, i.e. paragraph, code block etc. then add to content.
        if container of blocks, add a new paragraph (default)'''
        if not content.strip() == "": # skip empty lines
            Paragraph(self).add_content(content)

    def realize(self)->str:
        '''convert structure to HTML, for root this means adding every child together'''
        res = ""
        for child in self.children:
            res += child.realize() + "\n"
        return res
        
    def can_continue(self)->bool:
        '''checks if block can continue on next line, if it can it consumes the continuing marker.
        if it doesn't allow lazy lines, it also closes itself if it can't continue'''
        return True # root can always continue

    def check_for_new_block(self)->"Block|None":
        '''
        checks if a new leaf or container block can be started, if yes return that block, if no return none,
        (for lists, it creates list and list item and returns the list item)
        '''

        # filter out newlines:
        if Block.current_line.strip() == "": return

        if self.parse_verbatim: return # don't make any new blocks, rest is verbatim

        if self.is_indented_code_block(): # since indents take presidence
            return Indented_code_block(self)

        # block quote block:
        if self.is_block_quote_block():
            return Block_quote(self)
        
        
        
        

        if c := self.is_Setext_heading(): # takes precedence over thematic break
            # Setext should replace previous paragraph (done in constructor)
            
            return Setext_heading(self,c)

        if self.is_thematic_break(): # takes precedence over lists
            return Thematic_break(self)

        # list block:        
        if m := self.is_list_item():
            # now figure out if new block or not
            if isinstance(self, List_Block) and self.marker_belongs(m):
                # same list, keep going
                return List_item(self,m)
            else:
                # new list, "add" list_block (constructor takes care of proper ordering)
                b = List_Block(self,m)
                return List_item(b,m)
        
        if i := self.is_ATX_heading():
            return ATX_heading(self, i)
        
        if (c := self.is_fenced_code_block()):
            return Fenced_code_block(self, c) # type:ignore
        
        if (i := self.is_HTML_block()):
            return HTML_block(self, i)

        # if self.is_link_reference_definition():
        #     pass # TODO
        
        # if self.is_table_block():
        #     pass # TODO

        # else it's a paragraph or not a new block




    def is_block_quote_block(self)->bool:
        '''is the next line a new block quote.
        Block quotes defined by 0-3 indents followed by a carat: '>' and a space or tab,
         or single carat '>' followed by no space or tab
         if followed by a tab, that tab represents 3 spaces'''



        
        # remove whitespace (if it's more indents would have taken it)

        l = Block.current_line.lstrip(' ')
        if l[0] != '>': return False
        
        # check for space:
        if l[1] == ' ':
            Block.current_line = l[2:] # remove one space
            return True
        if l[1] == '\t': # tab replaced by ">   " of which "> " removed
            Block.current_line = "  " + l[2:]
            return True
        Block.current_line = l[1:]
        return True # nospace after caret

    def is_list_item(self)->str:
        '''is the next line a list item
        list items are indicated by a bullet list marker `-`, `+`, or `*`,
        or by an ordered list marker, which is a sequence of 1-9 digits followed by `.` or `)`
        returns marker including digits if true, empty string if false,
        the return includes extra indentation for catching subserquent blocks'''

        # it allows for 0-3 whitespace before, so:
        l = Block.current_line.lstrip()
        l = l.replace('\t', '   ') # expand tabs (This behaves strangely with the spec)


        if (c := l[0]) in ('-','+','*'):
            # figure out how much extra indentation:
            n_spaces = len(l[1:]) - len(l[1:].lstrip())
            if n_spaces == 0: return '' # not enough spaces
            n_spaces %= 4 # to remove potential codespaces
            # otherwise pass that on as part of marker:

            # remove marker
            Block.current_line = l[1 + n_spaces:]
            return c + ' ' * n_spaces

            
        # ordered:
        for d in ('.', ')'):
            n, c, _ = l.partition(d)
            if n.isnumeric() and len(n) < 10:
                # valid number, and a dot, check for spacing:
                i = l[len(n)+1:len(n)+6]
                n_spaces = len(i) - len(i.lstrip())
                if n_spaces == 5:
                    # that's code block, not extra indentation
                    Block.current_line = l[len(n) + 2:]
                    return n + c
                # otherwise pass that on as part of marker:
                if n_spaces > 0:
                    Block.current_line = l[len(n) + 1 + n_spaces:]
                    return n + c + ' ' * n_spaces
                # otherwise there's not enough spaces, it's not a list
                return ''
        return ''

    def is_thematic_break(self)->bool:
        '''is the next line a thematic break,
        thematic breaks are up to three spaces of indentation, followed by 3 or more 
        matching `-`, `_`, or `*` characters, followed by any number of spaces and tabs'''

        
        # now strip of whitespace and check for characters:
        l = Block.current_line.strip().replace(" ", "").replace("\t", "") # spaces and tabs allowed between

        if not ((c := l[0]) in ('-', '_', '*')):
            return False # not right character
        for c2 in l:
            if c2 != c:
                return False # other kind of character
        else:
            # ensure enough characters:
            if l.count(c) >= 3:
                return True # matches
            else: return False

    def is_ATX_heading(self)->int:
        '''is the next line an ATX heading,
        ATX headings are 0-3 indents, followed by 1-6 `#` characters, followed by non-zero whitespace, then an optional title,
        and an optional closing sequence of any number of `#` characters,
        the heading level is equal to the number of `#` characters in the opening sequence.
        
        Returns number of heading or 0 for false'''

        
        # count and strip initial `#`:
        l = Block.current_line.strip()
        llen = len(l)
        idx = 0
        while (idx < llen):
            if l[idx] != '#': break
            else: idx += 1
        if idx > 6: return 0 # too many
        if idx == 0: return 0 # too few
        if idx == llen: 
            Block.current_line = ''
            return idx # no title heading
        if not l[idx] in (' ', '\t'): return 0 # no space after `#` sequence

        # valid heading, strip trailing `#` and whitespace
        ls = l.rstrip('#')
        if not ls[-1] in (' ', '\t'):
            # not valid trailing, pass on as content:
            Block.current_line = l[idx:].strip()
        else:
            Block.current_line = ls[idx:].strip() # remove trailing `#` as well
        return idx # number of heading

    def is_Setext_heading(self)->str:
        '''is the next line an Setext heading,
        Setext heading indicators are up to three spaces of indentation, followed by 1 or more 
        matching `-` or `=` characters, followed by any number of spaces and tabs
        returns character if true and empty string if false'''

        # first check if it's a paragraph before this
        if not isinstance(self.open_child, Paragraph):
            return ''
        
        # now strip of whitespace and check for characters:
        l = Block.current_line.strip().replace(" ", "").replace("\t", "") # spaces and tabs allowed between
        if not ((c := l[0]) in ('-', '=')):
            return '' # not right character
        for c2 in l:
            if c2 != c:
                return '' # other kind of character
        else:
            return c # matches

    def is_indented_code_block(self)->bool:
        '''is the next line an indented code block,
        indented code blocks are lines beginning with 4 indentations, followed by arbitrary text'''

        # could probably be done nicer...

        st = Block.current_line[0:4].replace('\t', "    ") # expand all tabs

        if st[0:4] == "    ": # four indents, it's a block
            # remove the equivalent four from st and rejoin current line
            Block.current_line = st[4:] + Block.current_line[4:]
            return True
        else: return False
    
    def is_fenced_code_block(self)->str|bool:
        '''is the next line a fenced code block,
        fenced code blocks start with 0-3 indents followed by three of either `` ` `` or `~`,
        following the start, the next whitespace separated string is the info-string (rest of line discarded),
        after this the code block is ended by the same symbol, it may be ended on the same line (in which case there's no info string),
        if inline, the check fails and is treated in the inline part of parsing
        returns the type of delimiter if true else false
        '''
        # get rid of leading whitespace:
        l = Block.current_line.lstrip()

        if not ((c := l[0]) in ('`', '~')):
            return False # wrong character
        if not (l[0:3] == c+c+c):
            return False # doesn't match pattern

        if '`' in l[3:]: return False # not allowed in info string (for inline see inline parser)
        if c == '~' and '~' in l[3:]: return False # --||--

        # it's true so remove the actual fence
        Block.current_line = l[3:]

        return c
    
    def is_HTML_block(self)->int:
        '''is the next line a HTML block.
        seven conditions start and end a HTML block. this returns the number of the condition fulfilled, or 0 if not.
        contained text should be kept as is. line can also end same place it begins
        Also note! type 7 can't interrupt a paragraph'''
        l = Block.current_line.rstrip()
        
        one_tags = ["pre", "script", "style", "textarea"]
        six_tags = ["address", "article", "aside", "base", "basefont", "blockquote", "body", "caption", "center", "col",
                    "colgroup", "dd", "details", "dialog", "dir", "div", "dl", "dt", "fieldset", "figcaption", "figure",
                    "footer", "form", "frame", "frameset", "h1", "h2", "h3", "h4", "h5", "h6", "head", "header", "hr",
                    "html", "iframe", "legend", "li", "link", "main", "menu", "menuitem", "nav", "noframes", "ol",
                    "optgroup", "option", "p", "param", "search", "section", "summary", "table", "tbody", "td", "tfoot",
                    "th", "thead", "title", "tr", "track", "ul"]
        six_tags.extend(['/' + s for s in six_tags]) # closing tags allowed as well
        
        # two: HTML comment
        if l[0:4] == "<!--":
            return 2

        # three: PHP tag:
        if l[0:2] == "<?":
            return 3

        # four: other comment?
        if l[0:2] == "<!":
            return 4

        # five: CDATA:
        if l[0:9] == "<![CDATA[":
            return 5
        
        
        # one, six, seven: tag
        if l[0] == "<":
            tagname = l.split()[0][1:] # possible tagname including /
            
            # for one and six, check if tag is valid: (EOL or space,tab, or `>` after tag)
            if len(tagname) + 1 >= len(l) or l[len(tagname) + 1] in (' ', '\t', '>'):
                # valid tag can be 1-6
                if tagname in one_tags: return 1
                if tagname in six_tags: return 6

            # now if anything it's 7, which can't interrupt paragraph, so:
            if isinstance(self, Paragraph): return 0

            # for now just assume any tag is correct, ideally 7 should check
            # that the tag is correct, but for now just assume it is
            # TODO
            return 7
        
        return 0 

    
    def is_link_reference_definition(self)->bool:
        '''is the next line a link reference definition'''
        raise NotImplementedError()
    
    def is_table_block(self)->bool:
        '''is the next line a table block'''
        raise NotImplementedError()


    def __repr__(self) -> str:
        return self.__class__.__name__ + ": " + self.contents




class Block_quote(Block):

    is_containter:bool = True
    
    def can_continue(self) -> bool:
        '''same as a new block quote'''
        return self.is_block_quote_block()
    
    def realize(self) -> str:
        res = "<blockquote>\n"
        for child in self.children:
            res += child.realize() + '\n'
        return res + "</blockquote>"
    
class List_Block(Block):

    def __init__(self, parent: Block | None, marker:str) -> None:

        # make sure we're not nesting lists without list item between
        if isinstance(parent, List_Block):
            parent = parent.parent
        
        super().__init__(parent)
        self.marker = marker
    
    def marker_belongs(self, m:str)-> bool:
        '''check if a marker belongs to this list'''

        # bullets:
        if self.marker[0] in ('-','+','*'):
            # just check equality:
            return self.marker == m
        # ordered (remove value first)
        n,s,m = m.partition(' ')
        m = n[-1] + s + m # get rid of number
        n,s,my_m = self.marker.partition(' ')
        my_m = n[-1] + s + my_m
        return my_m == m
    
    def can_continue(self) -> bool:
        '''If next line can continue as list item, or is new list item, then we can continue.
        hot to check this without spoiling the line?'''
        #TODO:
        return True

    def realize(self) -> str:
        res = "<ul>\n" if (self.marker[0] in ('-','+','*')) else "<ol>\n"
        for child in self.children:
            res += child.realize() + '\n'
        return res + "</ul>" if (self.marker[0] in ('-','+','*')) else "</ol>"

    is_containter:bool = True

class List_item(Block):

    def __init__(self, parent: Block | None, marker:str) -> None:
        super().__init__(parent)
        self.marker = marker


    def can_continue(self) -> bool:
        '''to continue the list needs the right number of indents,
        number of indents is equal to the same column (after all other markers are removed)'''


        # expand tabs and get number of spaces:
        l =Block.current_line.replace('\t', '    ')
        n_space = len(l) - len(l.lstrip())
        req_space = len(self.marker)
        if n_space > req_space:
            # clean up marker:
            Block.current_line = l[req_space:]
            return True
        return False 
    
    def realize(self) -> str:

        # unpack paragraph if only content:
        if len(self.children) == 1 and isinstance(self.open_child, Paragraph):
            return "<li>" + inline_parse(self.open_child.contents) + "</li>"


        res = "<li>\n"
        for child in self.children:
            res += child.realize() + '\n'
        return res + "</li>"


    is_containter:bool = True

class Thematic_break(Block):

    def __init__(self, parent: Block) -> None:
        super().__init__(parent)
        self.open = False # thematic breaks don't have content

    def can_continue(self) -> bool:
        return False # thematic breaks are one line only
    
    def add_content(self, content: str):
        raise AttributeError("Can't add to thematic break")
    
    def realize(self) -> str:
        return "<hr />"


class ATX_heading(Block):

    def __init__(self, parent: Block, level:int) -> None:
        super().__init__(parent)
        self.level = level

    def can_continue(self) -> bool:
        self.open = False
        return False # ATX headings are one line only
    
    def add_content(self, content: str):
        self.contents += content

    def realize(self) -> str:
        return f"<h{self.level}>" + inline_parse(self.contents) + f"</h{self.level}>"

class Setext_heading(Block):

    def __init__(self, parent: Block, c:str) -> None:

        # check level:
        self.level = 1 if c == '=' else 2

        # grab paragraph as content
        p = parent.open_child # type:ignore
        self.contents = p.contents # type: ignore
        # delete paragraph:
        parent.children.remove(p) # type:ignore
        del(p)
        super().__init__(parent)

    def can_continue(self) -> bool:
        self.open = False
        return False # Setext are closed one created
    
    def realize(self) -> str:
        return f"<h{self.level}>" + inline_parse(self.contents) + f"</h{self.level}>"


class Indented_code_block(Block):

    parse_verbatim:bool = True

    def can_continue(self) -> bool:
        '''same as new code block'''
        return self.is_indented_code_block()
    
    def add_content(self, content: str):
        self.contents += content

    def realize(self) -> str:

        # trim empty lines: (should only trim start and end lines)
        l = '\n'.join(filter(None,self.contents.split('\n'))) 

        return "<pre><code>" + l + ("</code></pre>" if l[-1] == '\n' else "\n</code></pre>")

class Fenced_code_block(Block):

    parse_verbatim:bool = True

    def __init__(self, parent: Block, delimiter:str) -> None:
        self.delimiter = delimiter
        super().__init__(parent)


    def can_continue(self) -> bool:
        '''continues as long as we don't cee the breaking line'''

        if Block.current_line.strip() == self.delimiter * 3:
            Block.current_line = "" # Get rid of it from the end result
            return True
        else: return False

    def add_content(self, content: str):
        self.contents += content
    
    def realize(self) -> str:

        s = self.contents.split('\n')
        info = s.pop(0)
        self.contents = '\n'.join(filter(None,s)) # without first line and filtered
        info_s = (' class="language-' + info.split(' ')[0] + '"') if len(info) > 0 else ""

        return "<pre><code"+ info_s + ">" + self.contents + "\n</code></pre>"

class HTML_block(Block):

    parse_verbatim:bool = True
    
    def __init__(self, parent: Block, type:int) -> None:
        self.type = type
        super().__init__(parent)


    def can_continue(self) -> bool:
        '''7 different conditions, woah.
        If condition found add rest of line verbatim'''

        if self.type == 1: # closing tag
            for sub in ["</pre>", "</script>", "</style>", "</textarea>"]:
                if sub in Block.current_line.lower():
                    # it's the last line:
                    self.open = False
                    return True
        
        if self.type == 2:
            if "-->" in Block.current_line:
                # it's the last line:
                self.open = False
                return True
        
        if self.type == 3:
            if "?>" in Block.current_line:
                # it's the last line:
                self.open = False
                return True
                    
        if self.type == 4:
            if "!>" in Block.current_line:
                # it's the last line:
                self.open = False
                return True
        
        if self.type == 5:
            if "]]>" in Block.current_line:
                # it's the last line:
                self.open = False
                return True
        if self.type >= 6: # six or seven
            if Block.current_line.strip() == "":
                return False # no need to add empty line
        
        return True # if not stopped keep on reading
        
    def add_content(self, content: str):
        self.contents += content
    
    def realize(self) -> str:
        return self.contents


class Paragraph(Block):
    
    def can_continue(self) -> bool:
        if Block.current_line.strip() == "": 
            self.open = False # paragraph can't be lazy
            return False
        else: return True

    def add_content(self, content: str):
        self.contents += content

    def realize(self) -> str: # strip 0 to 3 spaces before
        return "<p>" + inline_parse(self.contents).lstrip() + "</p>"


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
            return self.content[self.idx-size: self.idx]
        except IndexError:
            return ''
    
    def move(self,pos):
        '''moves index by given amount'''
        self.idx += pos

def char_counter(s:fakestream, c:str)->int:
    '''counts length of char run, and sets stream to end of run.'''
    tick_len = 0
    while s.read(1) == c:
        tick_len += 1
    s.move(-1) # go back one
    return tick_len

NAME_PATTERN = r"[abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ01234567890-]+"
def is_valid_tag(tag:str)->bool:

    name = tag.split(' ')[0] # first part deliniated by space
    if not re.fullmatch(NAME_PATTERN, name): return False
    if not name[0].isalpha(): return False

    #TODO: attributes and closing tags
    return True    

delimeter_stack = []
def handle_link(out:str)->str:
    '''Handles links by looking in the delimiter stack'''
    for item in delimeter_stack[::-1]:
        if not item['type'] in ('[', '!['):
            continue
        elif not item['active']:
            delimeter_stack.remove(item)
            return ']'
        # found active delimiter, check if valid link TODO
        if False:
            pass

        else: 
            delimeter_stack.remove(item)
            return ']'
    # found nothing:
    return ']'

def process_emphasis(out:str,stack_bottom:int = -1):
    '''runs process emphasis, note that higher number is further into the stack'''
    added_space = 0


    curr_pos = stack_bottom+1
    openers_bottom = {'*' : stack_bottom, '_' : stack_bottom}
    while True:
        curr = delimeter_stack[curr_pos]
        if curr['dir'] < 0 or (not curr['type'] in ('*','_')):
            curr_pos += 1
            continue
        # else: we have a closer
        # look back for first matching:
        for i in range(curr_pos - max(stack_bottom, openers_bottom[curr['type']])):
            pot_opener = delimeter_stack[curr_pos-i]
            if not pot_opener['type'] == curr['type']:
                continue # doesn't match
            # else:
            
            # insert in opener:
            if pot_opener['length'] >= 2 and curr['length'] >= 2:
                out = out[:pot_opener['place']+added_space] + '<strong>' + out[pot_opener['place']+added_space:]
                added_space += len('<strong>')
            else:
                out = out[:pot_opener['place']+added_space] + '<em>' + out[pot_opener['place']+added_space:]
                added_space += len('<em>')
            
        else:
            # none found
            pass


def inline_parse(text:str)->str:
    '''applies the inline parsing rules, such as emphasis and line breaks.
    inline parsing is sequential so we can do it as a loop'''
    out = ""
    stream = fakestream(text)
    
    while (c := stream.read(1)) != '':

        # code spans:
        if c == '`':
            # count ticks:
            n = char_counter(stream, '`') + 1
            # found ticks, read into buffer until similar length found:
            buf = ''
            while (m := char_counter(stream, '`')) != n:
                # insert ticks literally:
                buf += '`'*m
                c = stream.read(1)
                if c == '': break # EOF
                buf += (c if c != '\n' else ' ') # remove newlines
            # broken
            if m == n:
                # found matching! strip buffer and put in out
                if len(buf) == buf.count(' '):
                    # only spaces, pass as is:
                    out += '<code>' + buf + '</code>'
                else:
                    # strip eventual first and last space
                    fs = (buf[0] != ' ')
                    ls = (buf[-1] != ' ')
                    out += '<code>' + buf[0]*fs + buf[1:-1] + buf[-1]*ls + '</code>'
            else:
                # ran into EOF, back up and insert literal backticks
                stream.move(-len(buf) - 1)
                out += '`' * n

            continue # in either case start parsing again

        # emphasis, links, and images:
        # using the common mark process, we enter these as literals now,
        # but mark them in the delimeter stack (process later) TODO
        if c in ('*', '_'): # emphasis
            # how long run?
            length = char_counter(stream, c) + 1
            # left and/or right? (neither and it's just literal)
            d = 0
            lor = False
            fol = stream.read(1)
            # left:
            if not (uni.category(fol) == 'Zs' or fol in ('\u0009','\u000A','\u000C','\u000D')):
                if not uni.category(fol) in ('P','S') or (uni.category(out[-1]) in ('Zs', 'P', 'S') or out[-1] in ('\u0009','\u000A','\u000C','\u000D')):
                    d -=1
                    lor = True
            
            # right:
            if not (len(out) == 0 or uni.category(out[-1]) == 'Zs' or out[-1] in ('\u0009','\u000A','\u000C','\u000D')):
                if not uni.category(out[-1]) in ('P','S') or (uni.category(fol) in ('Zs', 'P', 'S') or fol in ('\u0009','\u000A','\u000C','\u000D')):
                    d +=1
                    lor = True
            if lor: # add to stack
                # now add to stack:
                delimeter_stack.append({
                    "place": len(out),
                    "type": c,
                    "length": length,
                    "active": True,
                    "dir": d
                })

            # add literals and back up stream:
            stream.move(-1)
            out += c * length
            continue
        elif c in ('[', '!['): # TODO: integrate wiki-links
            delimeter_stack.append({
                    "place": len(out),
                    "type": c,
                    "length": len(c),
                    "active": True,
                    "dir": -1 # always for links
                })
            out += c
            continue
        elif c == ']':
            # out += handle_link(out)
            pass



        # raw HTML 
        # on `<`, find `>` and check if contents are valid html tag (with attributes)
        # if so, render verbatim, else, roll back stream and treat as literal `<`
        if c == '<':
            buf = ''
            while (c2 := stream.read(1)) != '>':
                buf += c2
                if c2 == '':
                    # reached EOF, so that's a false
                    stream.move(-len(buf)-1)
                    break

            if is_valid_tag(buf):
                out += '<' + buf + '>'
                continue
            else:
                stream.move(-len(buf)-1)
                # continue so `<` is picked up by html parser


        # breaks
        if c == '\n': 
            # find out if hard or soft.
            # if two spaces, or backslash, insert hard break
            # else soft break,
            # remove all space after in next line
            if out[-1] == '\\' or out[-2:] == '  ':
                out = out.rstrip(' ') + '<br />\n'
                # get rid of next spaces:
                while stream.read(1) == ' ': pass
                stream.move(-1) # move back to read new line
            # otherwise, clear out all space around it:
            else:
                out = out.rstrip(' ') + '\n'
                while stream.read(1) == ' ': pass
                stream.move(-1) # move back to read new line
            
            continue # next item



        # escaped ASCII (grab next as verbatim and put as c)
        if c == '\\':
            c = stream.read(1)
            if c in ('!', '"', '#', '$', '%', '&', "'", '(', ')', '*', '+', ',', '-', '.', '/', ':', ';', '<', '=', '>', '?', '@', '[', '\\', ']', '^', '_', '`', '{', '|', '}', '~'):
                # valid escaped character, put it through to next part:
                pass
            elif c == '\n':
                # special case hard break, handled above, so put literal and reset:
                out += '\\'
                stream.move(-1)
                continue
            else:
                # treat as normal character (no risk of being start of other inline trait)
                out += '\\' + c
                continue
        
        # valid HTML character references
        elif c == "&": # elif since otherwise an escaped & may get interpreted wrong
            # grab until semicolon:
            buf = ''
            while (c1 := stream.read(1)) != ';':
                if c1 == '': raise ValueError("uncompleted HTML character reference")
                buf += c1

            # is is a numerical code?
            try:
                if buf[0] == "#":
                    if buf[1] in ('X', 'x'):
                        # hex value:
                        num = int(buf[2:],16)
                    else:
                        num = int(buf[1:],10)
                    # now convert to unicode (unless zero in which case U+FFFD)
                    if num == 0: 
                        c = '\uFFFD'
                    else:
                        c = chr(num)
                # buffer is now content of the id
                elif '&' + buf + ';' in HTML_entites.keys():
                    c = HTML_entites['&' + buf + ';']["characters"]
                    # pass it on in case it's HTML sensitive
                else:
                    # not a HTML reference, go back and add it literally:
                    stream.move(-len(buf)-1)
            except ValueError:
                # invalid number code, print verbatim:
                out += '&' + buf + ';'
                continue
            

        # replace HTML sensitive with character references (and insecure unicode) (not  "'": "&apos;"?)
        HTML_replace = {'"': "&quot;", '&': "&amp;", '<': "&lt;", '>': "&gt;", '\u0000' : '\uFFFD'}
        if c in HTML_replace.keys():
            out += HTML_replace[c]
            continue


        out += c # nothing else just pass on text verbatim


    # now deal with emphasis TODO
    # process_emphasis(out)

    # clear out end breaks:
    if out[-7:] == "<br />\n": out = out[:-7]

    #clear end spaces:
    return out.rstrip()


def parse_md(text:StringIO)->str:
    '''
    Takes a string-input (like a file) comprising a .md document,
    and returns a string containing the equivalent
    HTML.  (perhaps make it a string output as well?)
    
    '''
    Block.init(text)
    while Block.read_line(): pass # read all lines

    return Block.root.realize()



if __name__ == "__main__":
    testcase = '''
The International Standard Atmosphere is a model of the atmosphere that is used to, well, model the atmosphere.

It is very important to have a model of the atmosphere, it allows you to calculate many different variables in many different conditions

# Geopotential altitude
All the below formulae, (and everything is atmospheric aerospace analysis) are based on gravity being constant with height
    
'''
    test_str = "code: `code`, cool code: `` cool` ``, space: ` ` tick: `` ` ``\n" \
    "inline: ```  ``code``  ```"
    print(inline_parse(test_str))
    # testcase = StringIO(testcase)
    # print(parse_md(testcase))

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

    def __init__(self,parent:"Block|None", contents:str = "") -> None:
        self.contents:str = contents
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
            # Setext should replace previous paragraph, so call on paragraph parent
            return Setext_heading(self.parent,c)

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
        l = Block.current_line.lstrip(' ')
        tabbed = (l[1] == "\t") # tabs assume a spacing of 1
        l = l.replace('\t', '   ',1) # expand tabs (including the '- ' for the first one)
        l = l.replace('\t', '    ')


        if (c := l[0]) in ('-','+','*'):
            # figure out how much extra indentation:
            n_spaces = len(l[1:]) - len(l[1:].lstrip(' '))
            if n_spaces == 0: return '' # not enough spaces
            n_spaces %= 4 # to remove potential codespaces
            # otherwise pass that on as part of marker:

            # remove marker
            if tabbed: n_spaces = 1

            Block.current_line = l[1 + n_spaces:]
            return c + ' ' * n_spaces

            
        # ordered:
        for d in ('.', ')'):
            n, c, _ = l.partition(d)
            if n.isnumeric() and len(n) < 10:
                # valid number, and a dot, check for spacing:
                i = l[len(n)+1:len(n)+6]
                n_spaces = len(i) - len(i.lstrip(' '))
                if n_spaces == 0: return ''
                if n_spaces == 5:
                    # that's code block, not extra indentation
                    Block.current_line = l[len(n) + 2:]
                    return n + c
                # otherwise pass that on as part of marker:
                if tabbed: n_spaces = 1
                Block.current_line = l[len(n) + 1 + n_spaces:]
                return n + c + ' ' * n_spaces
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
        if not isinstance(self, Paragraph):
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
        l = Block.current_line.lstrip(' ')

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
        n_space = len(l) - len(l.lstrip(' '))
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
        con = p.contents # type: ignore
        # delete paragraph:
        parent.children.remove(p) # type:ignore
        del(p)
        super().__init__(parent, con)

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
        return "<p>" + inline_parse(self.contents.lstrip(' ')) + "</p>"


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


def inline_parse(text:str)->str:
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

    out = [""] # improvement over v1, out is a list of strings
    # better this than a linked list and allows some pointer-like things
    stream = fakestream(text)
    
    while (c := stream.read(1)) != '':
        
        if (t := parse_inline_code(stream,c)):
            out.extend([t, '']) # type:ignore
            continue
        
        if (t := parse_inline_emphasis(stream,out,c)):
            out.extend([t, '']) # type:ignore
            continue

        if (t := parse_inline_links(stream,out,c)):
            out.extend([t, '']) # type:ignore
            # add new text string after to continue in (leave emphasis as it's own thing)
            continue

        if (t := parse_inline_HTML(stream,c)):
            out.extend([t, '']) # type:ignore
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
        out[-1] += HTML_sanitize(c)

    process_emphasis(out, -1)
    # remove end breaks:
    if out[-1][-7:] == "<br />\n": out[-1] = out[-1][:-7]
    # strip end spaces:
    out[-1] = out[-1].rstrip()

    return ''.join(out)

def parse_inline_code(stream:fakestream, c:str)->str|bool:
    '''read character, and if it's inline code, returns the resulting string.
    else returns false and backs up stream'''
    if c != '`': return False

    # count length of ticks:
    n = char_counter(stream, '`') + 1
    # found ticks, read into buffer until similar length found:
    buf = ''
    while (d := stream.read(1)) != '':
        if d != '`':
            # just insert regular characters (except make newlines to space)
            buf += (d if d != '\n' else ' ') 
            continue
        # else:
        m = char_counter(stream, '`') + 1 # number of ticks
        if m == n:
            # was matching, return buffer and tags
            return '<code>' + buf + '</code>'
        else:
            # just treat tags literally:
            buf += '`'*m
            continue
    # reached EOF, back up and ticks as literal:
    stream.move(-len(buf) - 1)
    return '`' * n

def parse_inline_HTML(stream:fakestream, c:str)->str|bool:
    '''read character, and if it's inline HTML, returns the resulting string.
    else returns falseand backs up stream'''
    if c != '<': return False
    buf = ''
    while (c2 := stream.read(1)) != '>':
        buf += c2
        if c2 == '':
            # reached EOF, so that's a false
            stream.move(-len(buf))
            return '&lt;'

    if is_valid_tag(buf):
        return '<' + buf + '>'
    else:
        stream.move(-len(buf))
        return '&lt;'

def parse_inline_linebreak(stream:fakestream, out:list[str], c:str)->bool:
    '''reads linbreak, and if it is figures out if it's soft or hard,
    then cleans out appropriately'''
    if c != '\n': return False


    # two+ spaces (or backslash, which is handles in escapes) hard break
    # else soft break
    if (len(out[-1])>=2 and out[-1][-2:0] == '  ') or (len(out[-1])>=1 and out[-1][-1] == '\t'):
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
    while stream.read(1) == ' ': pass
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
        return HTML_sanitize(c)
    
def parse_inline_char_ref(stream:fakestream, c:str):
    '''checks if the following is a valid HTML character unicode referece.
    if yes returns the unicode character, else move back stream
    and return false'''
    if c != '&': return False
    # grab until semicolon:
    buf = ''
    while (c1 := stream.read(1)) != ';':
        if c1 == '':
            # reached EOF, it's invalid so back up
            stream.move(-len(buf))
            return False
        buf += c1
    # figure out if it's valid:
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
                return '\uFFFD'
            else:
                return HTML_sanitize(chr(num))
        # buffer is now content of the id
        elif '&' + buf + ';' in HTML_entites.keys():
            return HTML_sanitize(HTML_entites['&' + buf + ';']["characters"])
        else:
            # not a HTML reference, go back and add it literally:
            stream.move(-len(buf) - 1)
            return False
    except (ValueError,IndexError):
        # invalid number code, go back:
        stream.move(-len(buf) - 1)
        return False



delimeter_stack = []
def parse_inline_emphasis(stream:fakestream, out:list[str], c:str)->str|bool:
    '''read character, if it starts emphasis, return an emphasis string
    and add to delimiter stack'''
    
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

def parse_inline_links(stream:fakestream,out:list[str], c:str)->str|bool:
    '''read character, if it starts link, return an emphasis string
    and add to delimiter stack, if it ends link, do the same'''
    if not c in ('[','!', ']'): return False
    
    # check for `![`:
    if stream.read(1) == '[':
        c = '!['
    else:
        stream.move(-1)
        return False # let someone else take it
    
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
        # check if valid link, valid link is:
        # - link text (already know is correct)
        # - link destination, text between `<>` with no `\n` or unescaped `<>`
        #   or nonempty sequence of chars, not including ASCII control chars, or space
        #   and only parentheses if they are escaped or make a balanced pair
        # - link title, delineated by `"`,`'`, or matching `()`,
        #   including only the delineator if escaped
        # links thake the form:
        # [text]( destination title )
        # with the spaces here allowed to be:
        # nonzero number of spaces and tabs, and up to one line ending.
        # this is then translated to:
        # <a href="destination" title="title">text</a>

        # images work the same, except they use alt instead of title, and 
        # "an image description may contain links"

        # TODO:
        # for now, return literal:
        return c


    else:
        # found none, insert literal:
        return c



def process_emphasis(out:list[str], stack_bottom:int = -1):
    '''Run process emphasis, until we reach indicated stack bottom'''
    curr_pos = stack_bottom+1
    openers_bottom = {'*' : stack_bottom, '_' : stack_bottom}
    global delimeter_stack

    while curr_pos < len(delimeter_stack):
        # get next closer:
        curr = delimeter_stack[curr_pos]
        if curr['dir'] < 0 or (not curr['type'] in ('*','_')):
            curr_pos += 1
            continue

        # look back for first matching, staying above bottom:
        for i in range(curr_pos- max(stack_bottom, openers_bottom[curr['type']])):
            pot = delimeter_stack[curr_pos-i] # potential opener
            if not (pot['type'] == curr['type'] and pot['dir']<=0 and pot != curr):
                continue # doesn't match
            # found valid one
            is_strong = len(out[curr['idx']]) >=2 and len(out[pot['idx']]) >=2
            
            # add emphasis or strong to nodes between delimeters:
            if is_strong:
                out[pot['idx']+1] = '<strong>' + out[pot['idx']+1]
                out[curr['idx']-1] += '</strong>'

                # remove delimeters from delimeter run:
                curr['length'] -= 2
                out[curr['idx']] = curr['type']*curr['length']
                pot['length'] -= 2
                out[pot['idx']] = pot['type']*pot['length']
            else:
                out[pot['idx']+1] = '<em>' + out[pot['idx']+1]
                out[curr['idx']-1] += '</em>'

                # remove delimeters from delimeter run:
                curr['length'] -= 1
                out[curr['idx']] = curr['type']*curr['length']
                pot['length'] -= 1
                out[pot['idx']] = pot['type']*pot['length']

            # remove all delimiters between opener and closer:
            for j in range(curr_pos-1, curr_pos-i, -1):
                delimeter_stack.pop(j)
                curr_pos-=1 # to keep it accurate

            # remove delimeters if they're empty:
            if pot['length'] == 0:
                delimeter_stack.remove(pot)
                curr_pos -=1
            if curr['length'] == 0:
                delimeter_stack.remove(curr)
                # move to next, which automatically happens with curr_pos
            break
        else: # none found
            openers_bottom[curr['type']] = curr_pos -1 # lower bound in future
            if curr['dir'] != 0:
                # not opener either, remove it
                # (which advances curr_pos)
                delimeter_stack.remove(curr)
            else:
                curr_pos += 1

            continue

    # remove delimeters above stack bottom TODO
    delimeter_stack = delimeter_stack[:stack_bottom+1]
    return;

def HTML_sanitize(c:str)->str:
    '''returns a sanitized version of the char as to not use symbols
    that might break HTML formatting'''
    HTML_replace = {'"': "&quot;", '&': "&amp;", '<': "&lt;", '>': "&gt;", '\u0000' : '\uFFFD'}
    if c in HTML_replace.keys():
        return HTML_replace[c]
    else: return c

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
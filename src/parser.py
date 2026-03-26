
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


import sys
directory = str(Path(__file__).parent.resolve()) # the src directory
sys.path.append(directory)
from utils import *
from inline import *

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

        # edge case:
        if isinstance(self.open_child, Link_reference):
            self.open_child.evaluate_ref()

        res = ""
        for child in self.children:
            res += child.realize() + "\n"
        # strip extra newlines:
        if (len(res) > 0) and (res[-1] == '\n'): return res.rstrip('\n') + '\n'
        else: return res
        
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
            elif isinstance(self,List_item) and self.parent.marker_belongs(m): # type:ignore
                # in case we're in the item
                return List_item(self.parent,m) # type:ignore
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

        if self.is_link_reference_definition():
            return Link_reference(self)
        
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
        if l[1] == '\t': # tab replaced by ">   " of which "> " removed (from the leftmost tab)
            l = l[-1:0:-1]
            l = l.replace('\t', '  ',1) # reverse l, replace, re-reverse
            l = l[::-1]
            Block.current_line = l
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
        # l = l.replace('\t', '    ')


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
        indented code blocks are lines beginning with 4 indentations, followed by arbitrary text.
        Indented code blocks cannot interrupt paragraphs'''

        if isinstance(self, Paragraph) and self.open: return False

        # if tab is involved, spaces before tabs are not carried through
        st = Block.current_line[0:4] # relevant part
        if st == '    ': # easiest option
            Block.current_line = Block.current_line[4:] # trim spaces
            return True
        elif '\t' in st:
            # keep spaces after tab
            sp = st.split('\t')
            if sp[0].lstrip(' ') != '': return False # has something other than tabs

            st = "".join(sp[1:]) # after first tab
            Block.current_line = st + Block.current_line[4:]
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
        
        one_tags = ["<pre", "<script", "<style", "<textarea"]
        six_tags = ["address", "article", "aside", "base", "basefont", "blockquote", "body", "caption", "center", "col",
                    "colgroup", "dd", "details", "dialog", "dir", "div", "dl", "dt", "fieldset", "figcaption", "figure",
                    "footer", "form", "frame", "frameset", "h1", "h2", "h3", "h4", "h5", "h6", "head", "header", "hr",
                    "html", "iframe", "legend", "li", "link", "main", "menu", "menuitem", "nav", "noframes", "ol",
                    "optgroup", "option", "p", "param", "search", "section", "summary", "table", "tbody", "td", "tfoot",
                    "th", "thead", "title", "tr", "track", "ul"]
        six_tags.extend(['/' + s for s in six_tags]) # closing tags allowed as well
        six_tags.extend([s + '/' for s in six_tags]) # and extra closing /
        
        # one: start of area
        # DOESN"T  WORK BECAUSE \n IS ALWAYS LAST, HAVE TO CHECK BEFORE THAT IS SPACE!!! TODO
        if l[-1] in (' ', '\t', '>', '\n') and l[:-1].lower() in one_tags:
            return 1

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
        
        # six: known tag (only needs to start with known tag)
        if l[0] == "<":
            if l.partition('>')[0][1:] in six_tags:
                return 6
        
        
            # seven: unknown tag
            # 7 can't interrupt paragraph, so:
            if isinstance(self, Paragraph): return 0

            if is_HTML_tag(l.rstrip()): # needs to be standalone tag
                return 7
        
        return 0 

    def is_link_reference_definition(self)->bool:
        '''is the next line a link reference definition.
        link references are comprised of a link label preceeded by 0-3 indentation
        then a colon `:`, then (with optional whitespace including up to one line break)
        a link destination, then (at least one whitespace)
        an optional link title. and no further elements.
        
        plan is to treat a potential link reference as link reference, then regress to paragraph is not
        (link reference also cannot interrupt a paragraph)'''

        # first check for label:
        l = Block.current_line.rstrip(' ')
        if l[0] != '[': return False
        label,_,rest = l[1:].partition(']') # rest may be empty if title continues
        if not valid_label_name(label): return False
        
        # now we don't know if the entire link is valid, but it's not invalid
        # treat it as valid and if not collapse it into a paragraph
        return True
    
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

    def __init__(self, parent: List_Block | None, marker:str) -> None:
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
            return "<li>" + inline_parse(self.open_child.contents, link_references) + "</li>"


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
        return f"<h{self.level}>" + inline_parse(self.contents, link_references) + f"</h{self.level}>"

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
        return f"<h{self.level}>" + inline_parse(self.contents, link_references) + f"</h{self.level}>"

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

        return "<pre><code>" + sanitize_text(l,False,False,True) + ("</code></pre>" if l[-1] == '\n' else "\n</code></pre>")

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
        info = sanitize_text(s.pop(0))
        self.contents = '\n'.join(filter(None,s)) # without first line and filtered
        info_s = (' class="language-' + info.split()[0] + '"') if len(info) > 0 else ""

        return "<pre><code"+ info_s + ">" + sanitize_text(self.contents, False, False, True) + "\n</code></pre>"

class HTML_block(Block):

    parse_verbatim:bool = True
    
    def __init__(self, parent: Block, type:int) -> None:
        self.type = type
        super().__init__(parent)

        # check if should close automatically:
        if not self.can_continue():
            self.open = False


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
        if not Block.current_line.strip() == "": return True
        self.open = False # paragraph can't be lazy
        return False

    def add_content(self, content: str):
        self.contents += content

    def realize(self) -> str: # strip 0 to 3 spaces before
        return "<p>" + inline_parse(self.contents.lstrip(' '), link_references) + "</p>"

link_references= [] # references have: label, link, and title
class Link_reference(Block):

    def can_continue(self) -> bool:
        if not Block.current_line.strip() == "": return True
        self.open = False # link reference can't be lazy
        self.evaluate_ref() # check if valid link
        return False
    
    def add_content(self, content: str):
        self.contents += content
    
    def evaluate_ref(self):
        '''check if link reference is valid, if it is, add to list of references, else
        regress to paragraph.'''
        if (t :=self.isvalid()):
            link_references.append({
                "label": label_collapse(t[0]), # type:ignore
                "dest": t[1], # type:ignore
                "title": t[2] # type:ignore
            })
            self.open = False # close yourself
        else:
            # revert to paragraph (create paragraph, give it contents, kill self)
            p = Paragraph(self.parent)
            p.open = False # we got closed so it's closed
            p.contents = self.contents
            self.parent.children.remove(self) # orphan yourself
            del(self) # kill yourself

    def isvalid(self)->tuple|bool:
        '''check if link reference is valid, if it is, add to list of references, else
        regress to paragraph.
         link references are comprised of a link label preceeded by 0-3 indentation
        then a colon `:`, then (with optional whitespace including up to one line break)
        a link destination, then (at least one whitespace)
        an optional link title. and no further elements.'''

        # for redundancy, check link label:
        cont = self.contents.lstrip(' ')
        if cont[0] != '[': return False
        
        label,_,rest = cont[1:].partition(']')
        if not valid_label_name(label): return False

        # check for colon:
        if not rest[0] == ':': return False
        else: rest = rest[1:] # remove colon

        # now rest has destination and title.
        rest = rest.lstrip() # remove whitespace
        if rest[0] == '<':
            # braced destination
            # find unescaped right brace
            m = re.search('(?<!\\)[>]',rest)
            if m is None: return False # no closing `<`
            # else:
            dest = rest[1:m.start()]
            title = rest[m.start():].strip()
        else: # non bracketed destination:
            count = 0
            dests = []
            for c in rest:
                if ord(c) <= 0x1F or c in ('\u007F', ' '): break # invalid character for destination
                # check for balanced parentheses:
                if c == '(': count += 1
                elif c == ')': count -=1
                if count < 0: return False # invalid parentheses
                dests.append(c)
            dest = "".join(dests)
            # apparently valid destination (if subsequent title is valid)
            title = rest[len(dest):].strip()
        if not valid_link_title(title): return False
        # finally if nothing shouted false, return values
        return label, dest, title[1:-1] # title trimmed of containers
    
    def realize(self) -> str:
        if self.open: self.evaluate_ref() # just in case we're last
        return '' # link references aren't printed


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
    
    test_str = '</imatag attr="woah" attr2="oh baby" _23 = true\n >'
    is_HTML_tag(test_str)
    # testcase = StringIO(testcase)
    # print(parse_md(testcase))
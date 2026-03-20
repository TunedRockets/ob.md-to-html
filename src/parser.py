
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
from warnings import warn
import re

class Block():

    input:StringIO
    root:"Block"
    current_line:str
    reread_line:bool
    is_containter:bool = True # for block-quotes and lists
    parse_verbatim:bool = False # for code and HTML blocks

    def __init__(self,parent:"Block|None") -> None:
        self.contents:str = ""
        self.open:bool = True # blocks are open unless otherwise specified
        
        
        if not parent is None:
            self.parent:"Block" = parent

            self.parent.children.append(self) # add child to parent
            self.parent.open_child = self # set onself as the open child

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

        # make sure we don't give a child to a paragraph
        if considered_blocks[-1].is_containter:
            potential_parent = considered_blocks[-1]
        else: potential_parent = considered_blocks[-2]

        # create new block if applicable ( and redo that if it was a containter):
        while (not (new_block := potential_parent.check_for_new_block()) is None):
            if not new_block.is_containter: break # leaf, keep going
            # else: add to list and go again
            considered_blocks.append(new_block)
        
        
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
        
        # list block:
        if self.is_list_start():
            return List_Block(self) # LEAVE LISTS FOR LATER!
        
        

        if self.is_Setext_heading(): # takes precidence over thematic break
            # Setext should replace previous paragraph
            warn("SETEXT NOT IMPLEMENTED YET!")
            pass

        if self.is_thematic_break():
            return Thematic_break(self)
        
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
        warn("BLOCK QUOTE NOT IMPLEMENTED PROPERLY YET!")


        
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
        return True # nospace after caret

    def is_list_start(self)->bool:
        '''is the next line a new list start
        (note that checking if it continues a list is already done)
        List is indicated by 
        '''
        warn("LIST NOT IMPLEMENTED YET!")
        return False

        raise NotImplementedError()

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
            return True # matches

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
        if l[idx] != ' ': return 0 # no space after `#` sequence

        # valid heading, strip trailing `#` and whitespace
        ls = l.rstrip('#')
        if not ls[-1] in (' ', '\t'):
            # not valid trailing, pass on as content:
            Block.current_line = l[idx:].strip()
        else:
            Block.current_line = ls[idx:].strip() # remove trailing `#` as well
        return idx # number of heading

    def is_Setext_heading(self)->bool:
        '''is the next line an Setext heading,
        Setext heading indicators are up to three spaces of indentation, followed by 3 or more 
        matching `-` or `=` characters, followed by any number of spaces and tabs'''
        
        # now strip of whitespace and check for characters:
        l = Block.current_line.strip().replace(" ", "").replace("\t", "") # spaces and tabs allowed between
        if not ((c := l[0]) in ('-', '=')):
            return False # not right character
        for c2 in l:
            if c2 != c:
                return False # other kind of character
        else:
            return True # matches

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

        if '`' in l[3:]: return False # not allowed in info string
        if c == '~' and '~' in l[3:]: return False # --||--

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

    is_containter:bool = True

class List_item(Block):
    is_containter:bool = True

class Thematic_break(Block):

    is_containter:bool = False

    def __init__(self, parent: Block) -> None:
        super().__init__(parent)
        self.open = False # thematic breaks don't have content

    def can_continue(self) -> bool:
        return False # thematic breaks are one line only
    
    def add_content(self, content: str):
        raise AttributeError("Can't add to thematic break")
    
    def realize(self) -> str:
        return "<hr/>"


class ATX_heading(Block):

    is_containter:bool = False

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

class Indented_code_block(Block):

    is_containter:bool = False
    parse_verbatim:bool = True

    def can_continue(self) -> bool:
        '''same as new code block'''
        return self.is_indented_code_block()
    
    def add_content(self, content: str):
        self.contents += content

    def realize(self) -> str:
        return "<pre><code>" + self.contents + "</code></pre>" if self.contents[-1] == '\n' else "\n</code></pre>"

class Fenced_code_block(Block):

    is_containter:bool = False
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
        return "<pre><code>" + self.contents + "\n</code></pre>"

class HTML_block(Block):

    is_containter:bool = False
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

    is_containter:bool = False
    
    def can_continue(self) -> bool:
        if Block.current_line.strip() == "": return False
        else: return True

    def add_content(self, content: str):
        self.contents += content

    def realize(self) -> str:
        return "<p>" + inline_parse(self.contents) + "</p>"


def inline_parse(text:str)->str:
    '''applies the inline parsing rules, such as emphasis and line breaks'''

    # for now just strip leading and trailing whitespace on each new line
    l = text.split('\n')
    s = lambda x: x.strip() 
    l = map(s,l)
    l = '\n'.join(filter(None,l))
    return l


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
    testcase = StringIO(testcase)
    print(parse_md(testcase))
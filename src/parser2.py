
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

def parse_md(text:StringIO)->str:
    '''
    Takes a string-input (like a file) comprising a .md document,
    and returns a string containing the equivalent
    HTML.  (perhaps make it a string output as well?)
    
    '''
    Block.init(text)
    while Block.read_line(): pass # read all lines

    return Block.root.realize()




class Block():

    input:StringIO
    root:"Block"
    current_line:str
    current_open:"Block"

    def __init__(self,parent:"Block|None", contents:str = "") -> None:
        self.contents:str = contents
        self.open:bool = True # blocks are open unless otherwise specified
        
        
        if not parent is None:

            # make sure parent can hold stuff (otherwise ask their parent)
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
        1. check if current open can stay open,
        if it cant, close it and move open up a level, if it can (lazily), pass that on.
        if any block is lazy, it's children must be lazy as well
        2. if it can, next check if new line can cause an interruption
        2a. if no add to open and move on
        2b. if yes, check if it interrupts inside or outside, then set that as open and check
        the line again.

        returns true on successful read, and false if EOF is reached.
        '''

        # get new line:
        Block.current_line = Block.input.readline()

        # get deepest open: (0:closed, 1:lazy, 2:open)
        b = Block.root
        o_list = []
        while not (b.open_child) is None:
            o_list.append(b.can_continue())
            b = b.open_child
        o_list.append(b.can_continue())
        while True:
            # b is lowest, if they can continue we close them and go up the tree
            if o_list[-1] == 0:
                # b can't continue
                b.open = False
                o_list.pop()
                b = b.parent
                continue # return to start
            # else: b is open or lazy, check for interrupts
            for t in Block.__subclasses__():
                if t.can_interrupt(b, o_list[-1]):
                    # add new block to the stack:
                    b:Block = b.open_child # type:ignore
                    o_list.append(b.can_continue()) 
                    break # this falls past the else into a continue
            else:
                # did not find any interrupt, add content to open
                pass
                break
            continue
        # end while:
        # add content to open:
        b.add_content(Block.current_line)
        return True # start on next line
        


        
    @staticmethod
    def can_interrupt(b:"Block", laziness:int)->bool:
        '''Checks whether the class can interrupt the current block
        if it can, do so and return true,
        else return false'''
        raise NotImplementedError("root can't interrupt")
    
    def can_continue(self)->int:
        '''Checks if block can continue on next line, and consumes any indicative markers
        lazy lists and quote blocks will return the conditional 1, indicating lazyness.
        it will still consume indents for lazyness, if parent is lazy then child is lazy as well
        if false, will not consume anything and return 0'''
        return True # root can always continue

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
        
    

  

    def __repr__(self) -> str:
        return self.__class__.__name__ + ": " + self.contents

# order of subclasses indicates precedence:


class ATX_heading(Block):

    def __init__(self, parent: Block, level:int) -> None:
        super().__init__(parent)
        self.level = level

    def can_continue(self) -> int:
        return 0 # ATX headings are one line only
    
    @staticmethod
    def can_interrupt(b:"Block", laziness:int)->bool:
        '''headings can only interrupt "standard" blocks
        
        ATX headings are 0-3 indents, followed by 1-6 `#` characters, followed by non-zero whitespace, then an optional title,
        and an optional closing sequence of any number of `#` characters,
        the heading level is equal to the number of `#` characters in the opening sequence.
        '''
        # check indent:
        if Block.current_line[0:4].replace('\t','    ').strip() == '': return False # too much indent

        
        # count and strip initial `#`:
        l = Block.current_line.strip()
        llen = len(l)
        idx = 0
        while (idx < llen):
            if l[idx] != '#': break
            else: idx += 1
        if idx > 6: return False # too many
        if idx == 0: return False # too few
        if not l[idx] in (' ', '\t'): return False # no space after `#` sequence
        
        # strip `#` from content and set as open
        l = l.lstrip('#')
        

        # valid heading, strip trailing `#` and whitespace
        ls = l.rstrip('#')
        if not ls[-1] in (' ', '\t'):
            # not valid trailing, pass on as content:
            Block.current_line = l[idx:]
        else:
            Block.current_line = ls[idx:] # remove trailing `#` as well

        new = ATX_heading(b,idx)
        return True

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

    @staticmethod
    def can_interrupt(b:"Block", laziness:int)->bool:
        '''headings can only interrupt "standard" blocks
        
        Setext heading indicators are up to three spaces of indentation, followed by 1 or more 
        matching `-` or `=` characters, followed by any number of spaces and tabs
        returns character if true and empty string
        '''
        # setext only interrupts paragraphs (and not lazy ones)
        if not isinstance(b, Paragraph) or laziness == 1:
            return False


        # check indent:
        if Block.current_line[0:4].replace('\t','    ').strip() == '': return False # too much indent

        
        # now strip of whitespace and check for characters:
        l = Block.current_line.strip() # spaces not allowed inside
        if not ((c := l[0]) in ('-', '=')):
            return False # not right character
        for c2 in l:
            if c2 != c:
                return False # other kind of character
        # else:
        
        new = Setext_heading(b,c)
        return True

    def can_continue(self) -> int:
        return 0 # Setext are closed once created
    
    def realize(self) -> str:
        return f"<h{self.level}>" + inline_parse(self.contents, link_references) + f"</h{self.level}>"

class Thematic_break(Block):

    def __init__(self, parent: Block) -> None:
        super().__init__(parent)

    def can_continue(self) -> int:
        return 0 # thematic breaks are one line only
    
    @staticmethod
    def can_interrupt(b:"Block", laziness:int)->bool:
        '''Thematic breaks interrupt only paragraphs or quotes/list-items
        thematic breaks are up to three spaces of indentation, followed by 3 or more 
        matching `-`, `_`, or `*` characters, followed by any number of spaces and tabs'''

        if not type(b) in (Paragraph, Block_quote, List_item):
            return False

        # check indent:
        if Block.current_line[0:4].replace('\t','    ').strip() == '': return False # too much indent


        # now strip of whitespace and check for characters:
        l = Block.current_line.strip().replace(" ", "").replace("\t", "") # spaces and tabs allowed between

        if not ((c := l[0]) in ('-', '_', '*')):
            return False # not right character
        for c2 in l:
            if c2 != c:
                return False # other kind of character
        # else:
            # ensure enough characters:
        if l.count(c) < 3: return False # too few

        Block.current_line = ''
        new = Thematic_break(b)
        return True

            
    def add_content(self, content: str):
        pass # can't add content to themaic break
    
    def realize(self) -> str:
        return "<hr />"

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
    
    def can_continue(self) -> int:
        '''If next line can continue as list item, or is new list item, then we can continue.
        HOW DO?'''
        # if a new item can be made, or an item can continue, then it's fine
        if List_item.can_interrupt(self, 2,peek=True):
            return 2
        elif self.open_child.can_continue(peek=True): # type:ignore
            return 2
        else: return 0
    
    @staticmethod
    def can_interrupt(b:Block, laziness:int)->bool:
        '''Lists can only interrupt paragraph or containter
        Lists can only start if there's a new list item.
        critically they don't remove the marker, that's for the item to do'''
        #TODO: same logic as list item

        if not type(b) in (Paragraph, Block_quote, List_item):
            return False

        # if list item could interrupt then i can as well:
        if List_item.can_interrupt(b, laziness,peek=True):
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


    def can_continue(self, peek:bool=False) -> int:
        '''to continue the list needs the right number of indents,
        number of indents is equal to the same column (after all other markers are removed)'''

        #TODO: does this worlk
        # expand tabs and get number of spaces:
        l =Block.current_line.replace('\t', '    ')
        n_space = len(l) - len(l.lstrip(' '))
        req_space = len(self.marker)
        if n_space > req_space:
            # clean up marker:
            if not peek: Block.current_line = l[req_space:]
            return 2
        return 0 
    
    @staticmethod
    def can_interrupt(b: Block, laziness: int, peek:bool=False) -> bool:
        '''list items can only occur in lists, but a list item existing does
        indicate that a new list can begin
        
        list items are indicated by a bullet list marker `-`, `+`, or `*`,
        or by an ordered list marker, which is a sequence of 1-9 digits followed by `.` or `)`
        
        peek means the marker is not removed from the line, and it doens't care what b is
        '''
        if not type(b) == List_Block and not peek:
            return False

        # check indent:
        if Block.current_line[0:4].replace('\t','    ').strip() == '': return False # too much indent

        l = Block.current_line.lstrip().replace('\t', '  ',1) # in case there is a tab

        # figure out the marker: (marker is followed by 1-4 spaces, if more then
        # count as no spaces and the rest is a code-block)
        if (c := l[0]) in ('-','+','*'):

            n_spaces = len(l[1:]) - len(l[1:].lstrip(' '))
            if n_spaces == 0: return False # not enough spaces
            elif n_spaces > 4: n_spaces = 1 # rest is code block

            mkr = c + ' ' * n_spaces
            
            if not peek: 
                Block.current_line = Block.current_line[len(mkr):]
                new = List_item(b,mkr) #type:ignore
            return True

        # match ordered list:
        ORD_MATCH = r'[0-9]{1,9}[\.\)]'
        if m:= re.match(ORD_MATCH, l):
            i = int(m[0][:-1])
            n_spaces = len(l[len(m[0]):]) - len(l[len(m[0]):].lstrip(' '))
            if n_spaces == 0: return False # not enough spaces
            elif n_spaces > 4: n_spaces = 1 # rest is code block

            mkr = m[0] + ' ' * n_spaces
            
            if not peek: 
                Block.current_line = Block.current_line[len(mkr):]
                new = List_item(b, mkr) #type:ignore
            return True
        return False # not ordered or unordered.

        
    
    def realize(self) -> str:

        # unpack paragraph if only content:
        if len(self.children) == 1 and isinstance(self.open_child, Paragraph):
            return "<li>" + inline_parse(self.open_child.contents, link_references) + "</li>"


        res = "<li>\n"
        for child in self.children:
            res += child.realize() + '\n'
        return res + "</li>"


    is_containter:bool = True


class Block_quote(Block):


    @staticmethod
    def can_interrupt(b: Block, laziness: int, peek=False) -> bool:
        '''can a block quote go here?
        
        Block quotes defined by 0-3 indents followed by a carat: '>' and a space or tab,
         or single carat '>' followed by no space or tab
         if followed by a tab, that tab represents 3 spaces'''
        
        if not type(b) in (Paragraph, List_item, Block_quote):
            return False
        # check indent:
        if Block.current_line[0:4].replace('\t','    ').strip() == '': return False # too much indent

        # eat whitespace, eat carat, eat ev space ( or tab)
        l = Block.current_line.lstrip(' ')
        if l[0] != '>': return False

        if l[1] == ' ':
            # one space, remove it
            l = '>' + l[2:]
        elif l[1] == '\t':
            # tab is equal to two (?) spaces, since a space and caret are included in it
            l = l.replace('\t', '  ',1)
        Block.current_line = l # eat marker
        if not peek: new = Block_quote(b)
        return True
    
    def can_continue(self) -> int:
        '''if we have caret then remove it and continue, else it is lazy'''

        if self.can_interrupt(self,2,peek=True):
            return 2
        else: return 1 # lazy
    
    def realize(self) -> str:
        res = "<blockquote>\n"
        for child in self.children:
            res += child.realize() + '\n'
        return res + "</blockquote>"
   


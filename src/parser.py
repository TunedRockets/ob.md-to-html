
from io import StringIO
import re
import unicodedata as uni

# grab HTML entities:
from pathlib import Path
import json
from typing import overload


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
    global link_references
    link_references = []

    Block.init(text)
    while Block.read_line(): pass # read all lines

    Link_reference.evaluate_all()

    return Block.root.realize()




class Block():

    input:StringIO
    root:"Block"
    current_line:str
    current_open:"Block"

    def __init__(self,parent:"Block|None", contents:str = "") -> None:
        self.contents:str = contents
        self.open:bool = True # blocks are open unless otherwise specified
        self.lazy:bool = False # needed for some minor cases

        # looseness:
        if hasattr(parent, "mayloose"):
            if parent.mayloose: parent.loose = True # type:ignore

        
        if not parent is None:

            # don't want to be child to paragraph or link reference (only time that would matter)
            if type(parent) in (Link_reference, Paragraph): parent = parent.parent

            self.parent:"Block" = parent

            self.parent.children.append(self) # add child to parent
            self.parent.open_child = self # set oneself as the open child
        else:
            # for the root:
            self.parent = None #type:ignore
            self.is_containter = True
        self.children:list["Block"] = []
        self.open_child:"Block|None" = None

    @staticmethod
    def init(input:StringIO):
        Block.root = Block(None)
        Block.input = input
        Block.reread_line = False
        Link_reference.link_instances = []

    def is_lazy(self, indent:int)->bool:
        '''checks if current line is possibly a lazy continuation line,
        used for lists and quotes.
        
        Lazy continuation lines are "paragraph continuation lines"
        meaning lowest open child is a paragraph, and nothing can interrupt that,,
        indent is applied before rest of line is parsed, this is for block quotes
        because the block quote marker space is lazily included,
        may be the same for lists.
        also flips the lazy bool (before checking for interrupts)'''
        if self.open_child is None: return False # have no child to continue
        if Block.current_line.strip() == '': return False # empty lines break laziness

        low_child = self.open_child
        while not low_child.open_child is None:
            low_child = low_child.open_child # get lowest open child
        
        if not (isinstance(low_child, Paragraph) and low_child.open):
            return False # not open paragraph

        # put in extra space (for interpretation purposes):
        Block.current_line = ' ' * indent + Block.current_line
        self.lazy = True

        for t in Block.__subclasses__(): # make sure nothing is interrupting the low child
            if t.can_interrupt(low_child, peek = True):
                self.lazy = False
                return False
        else: 
            return True

    def is_loose(self)->bool:
        '''check if current line/status is conducive to looseness.
        which requires an empty line, and a closed open_child or one that can't continue'''
        if not Block.current_line.strip() == '': return False
        if self.open_child is None: return False
        if not self.open_child.open: return True
        if self.open_child.can_continue(peek=True): return False
        else: return True
        

    @staticmethod
    def read_line()->bool:
        '''
        reads a new line from the input and updates the block tree.
        
        returns true on successful read, and false if EOF is reached.
        '''

        # get new line:
        Block.current_line = Block.input.readline()

        if Block.current_line == '': return False # EOF


        b = Block.root

        while not (b.open_child) is None:
            if b.open_child.open and b.open_child.can_continue(): # if manually closed we break
                b = b.open_child
            else:
                break # child is closed
        # now b is lowest open that doesn't have open child
        b:Block # for intellisense
        while True:
            for t in Block.__subclasses__():
                if not (new := t.can_interrupt(b)) is None:

                    # new block is now the lowest open
                    if new.can_continue(): # if it can't then return to 
                        b = new 
                    else:
                        b = new.parent #?
                    break # this falls past the else into a continue
            else:
                # did not find any interrupt, add content to open
                break
            continue
        # end while:
        # add content to open:
        b.add_content(Block.current_line)
        return True # start on next line
        

    def reparent(self, new_parent:"Block"):
        '''reparent this block to a new parent,
        old parent's open child will become none, but
        this should only be called to reparent off of a closed parent anyways'''
        self.parent.children.remove(self)
        new_parent.children.append(self)
        new_parent.open_child = self
        self.parent = new_parent
        return; 


    @staticmethod
    @overload
    def can_interrupt(b, peek=False)->"Block|None":...
    @staticmethod
    @overload
    def can_interrupt(b, peek=True)->"bool|None":... 
    
    @staticmethod
    def can_interrupt(b:"Block", peek=False)->"Block|None|bool":
        '''Checks whether the class can interrupt the current block
        if it can, do so and return true,
        else return false'''
        raise NotImplementedError("root can't interrupt")
    
    def can_continue(self, peek=False)->int:
        '''Checks if block can continue on next line, and consumes any indicative markers.'''
        
        return 2 # root can always continue

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
            res += child.realize()
            res += '\n' if (len(res)>0 and res[-1] != '\n') else '' # make sure each is separated by newline
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

    def can_continue(self, peek=False) -> bool:
        if self.open:
            self.open = False
            return True
        else: return False # ATX headings are one line only
    
    @staticmethod
    def can_interrupt(b:"Block", peek=False)->"ATX_heading|None|bool":
        '''headings can only interrupt "standard" blocks
        
        ATX headings are 0-3 indents, followed by 1-6 `#` characters, followed by non-zero whitespace, then an optional title,
        and an optional closing sequence of any number of `#` characters,
        the heading level is equal to the number of `#` characters in the opening sequence.
        '''

        if not type(b) in (Block, Paragraph, Block_quote, List_item, Link_reference):
            return None

        # check indent:
        if Block.current_line[0:4].replace('\t','    ').strip() == '': return None # too much indent

        
        # count and strip initial `#`:
        l = Block.current_line.strip()
        llen = len(l)
        idx = 0
        while (idx < llen):
            if l[idx] != '#': break
            else: idx += 1
        if idx > 6: return None # too many
        if idx == 0: return None # too few
        if len(l) > idx and (not l[idx] in (' ', '\t')): return None # no space after `#` sequence
        
        # strip `#` from content
        l = l.lstrip('#')
        

        # valid heading, strip trailing `#` and whitespace
        ls = l.rstrip('#')
        if ls == '' or (ls[-1] in (' ', '\t')):
            # valid trailing, cut it off:
            l = ls
        if not peek:
            Block.current_line = '' # eat line
            new = ATX_heading(b,idx)
            new.add_content(l) # add the content
            return new
        else: return True

    def add_content(self, content: str):
        self.contents += content

    def realize(self) -> str:
        return f"<h{self.level}>" + inline_parse(self.contents, link_references) + f"</h{self.level}>"

SETEXT_RE = r'^(-+|=+)$' # TODO: test
class Setext_heading(Block):

    def __init__(self, parent: Block, c:str) -> None:

        # check level:
        self.level = 1 if c == '=' else 2

        # grab paragraph
        if isinstance(parent, Paragraph):
            p = parent
            parent = p.parent
        else: p = parent.open_child # type:ignore
        con = p.contents # type: ignore
        # delete paragraph:
        parent.children.remove(p) # type:ignore
        del(p)
        super().__init__(parent, con)

    @staticmethod
    def can_interrupt(b:"Block", peek=False)->"Setext_heading|None|bool":
        '''headings can only interrupt "standard" blocks
        
        Setext heading indicators are up to three spaces of indentation, followed by 1 or more 
        matching `-` or `=` characters, followed by any number of spaces and tabs
        returns character if true and empty string
        '''
        # setext only interrupts paragraphs (and link references)
        if type(b) == Block: # edge case where we made new paragraph
            if isinstance(b.open_child, Paragraph) and b.open_child.open:
                # that's the real deal
                b = b.open_child

        if not type(b) in (Paragraph, Link_reference): return None

        # not in lazy continuations
        if b.parent.lazy: return None
        


        # check indent:
        if Block.current_line[0:4].replace('\t','    ').strip() == '': return None # too much indent

        
        # now strip of whitespace and check for characters:
        
        l = Block.current_line.strip() # spaces not allowed inside
        
        m = re.match(SETEXT_RE, l) # if setext it will match
        if m is None: return None
        # else:
        c = l[0]
        # else:
        # Block.current_line = '' don't eat now, eat later
        if peek:
            return True # link is peeking ahead, don't actually make a new
        new = Setext_heading(b,c)
        return new

    def can_continue(self, peek=False) -> bool:
        if self.open:
            self.open = False
            return True
        else: return False # Setext headings are one line only

    def add_content(self, content: str):
        pass # already grabbed the content, eat underline line
    
    def realize(self) -> str:
        return f"<h{self.level}>" + inline_parse(self.contents, link_references) + f"</h{self.level}>"

class Thematic_break(Block):

    def __init__(self, parent: Block, list_interrupt:bool=False) -> None:

        if list_interrupt:
            # gotta go another layer up
            parent = parent.parent

        super().__init__(parent)

    def can_continue(self, peek=False) -> int:
        if self.open:
            self.open = False
            return True
        else: return False # thematic breaks are one line only
    
    @staticmethod
    def can_interrupt(b:"Block", peek=False)->"Thematic_break|None|bool":
        '''Thematic breaks interrupt only paragraphs or quotes/list-items
        thematic breaks are up to three spaces of indentation, followed by 3 or more 
        matching `-`, `_`, or `*` characters, followed by any number of spaces and tabs'''

        if not type(b) in (Block, Paragraph, Block_quote, List_item, List_Block, Link_reference):
            return None
        
        
        list_interrupt =(type(b) == List_Block)
        # special case, has to go out a layer when instancing

        # check indent:
        if Block.current_line[0:4].replace('\t','    ').strip() == '': return None # too much indent


        # now strip of whitespace and check for characters:
        l = Block.current_line.strip().replace(" ", "").replace("\t", "") # spaces and tabs allowed between

        if not ((c := l[0]) in ('-', '_', '*')):
            return None # not right character
        for c2 in l:
            if c2 != c:
                return None # other kind of character
        # else:
            # ensure enough characters:
        if l.count(c) < 3: return None # too few

        # Block.current_line = '' don't eat now, eat later
        if peek: return True
        new = Thematic_break(b, list_interrupt)
        return new

            
    def add_content(self, content: str):
        pass # can't add content to themaic break (eats line)
    
    def realize(self) -> str:
        return "<hr />"

class List_Block(Block):

    def __init__(self, parent: Block | None, marker:str) -> None:

        # make sure we're not nesting lists without list item between
        if isinstance(parent, List_Block):
            parent = parent.parent
        
        super().__init__(parent)
        self.marker = marker
        self.loose = False
        self.mayloose = False
        '''A list is loose if any of it's constituents are separated by blank lines, or if any item directly contains
        two block-level elements with a blank line between them'''
    
    def marker_belongs(self, m:str)-> bool:
        '''check if a marker belongs to this list,
        note that indentation before marker need only be at least as much
        not match'''

        # bullets:
        if (c:=self.marker.lstrip()[0]) in ('-','+','*'):
            # check indent and equality:
            my_ind,_,_ = self.marker.partition(c)
            ind,c2,_ = m.partition(c)
            # if c matches, c2 is not empty
            if c2 == '': return False

            #it matches, now my_ind should be smaller than ind
            return my_ind in ind
        # ordered (remove value first)
        if '.' in self.marker: c = '.' 
        else: c = ')'

        bef, dot, aft = self.marker.partition(c)
        my_space = ' ' * (len(bef) - len(bef.lstrip(' '))) # just spaces
        my_m = dot + aft

        bef, dot, aft = m.partition(c)
        space = ' ' * (len(bef) - len(bef.lstrip(' ')))
        m = dot + aft
        return (my_m == m) and my_space in space # at least as long
    
    

    def can_continue(self, peek=False) -> bool:
        '''If next line can continue as list item, or is new list item, then we can continue.
        '''
        # if a new item can be made (of same marker), or an item can continue, then it's fine,
        # and blank lines can also continue

        if self.is_loose() and not peek:
            self.mayloose = True
        elif not peek:
            self.mayloose = False
        
        
        if m:= List_item.can_interrupt(self,peek=True): # new item
            if self.marker_belongs(m): return True

        
        if self.open_child.can_continue(peek=True): # type:ignore
            return True # same item
        
        

        # else: 
        return False
    
    @staticmethod
    def can_interrupt(b:Block, peek=False)->"List_Block|None|bool":
        '''Lists can only interrupt paragraph or containter
        Lists can only start if there's a new list item.
        critically they don't remove the marker, that's for the item to do'''

        if not type(b) in (Block, Paragraph, Block_quote, List_item, Link_reference):
            return None
        

        # if list item could interrupt then i can as well:
        if m := List_item.can_interrupt(b,peek=True):

            if Block.current_line.partition(m)[2].strip() == '' and isinstance(b,Paragraph):
                return None # we can't interrupt paragraphs
            if peek: return True
            new = List_Block(b,m)
            return new
        else: return None
        

    def realize(self) -> str:


        # check if any child is loose (then i should be loose:)
        for child in self.children:
            if child.loose: self.loose = True #type: ignore

        if self.marker.lstrip()[0] in ('-','+','*'):
            start = '<ul>\n'
            end = '</ul>'
        else:
            # figure out start number if not 1:
            n = int(re.search(r'[0-9]+', self.marker)[0]) # type:ignore
            if n != 1:
                start = f'<ol start="{n}">\n'
            else: start = '<ol>\n'
            end = '</ol>'


        res = start
        for child in self.children:
            res += child.realize() + '\n'
        return res + end

    is_containter:bool = True


class List_item(Block):

    def __init__(self, parent: List_Block | None, marker:str) -> None:
        super().__init__(parent)
        self.marker = marker
        self.startline = True
        self.mayloose = False # for looseness
        self.loose = False
        


    def can_continue(self, peek:bool=False) -> bool:
        '''to continue the list needs the right number of indents,
        number of indents is equal to the same column (after all other markers are removed)'''
        # we can also be lazy, in which case we still return true on a paragraph continuation text
        if not self.open: return False

        if not peek and self.startline: # to ensure it can continue on the first line
            self.startline = False
            self.twoline = Block.current_line.strip() == ''
            self.lazy = False
            return True
        if not peek and self.twoline and Block.current_line.strip() == '':
            self.open = False
            return False # can't have two empty lines
        
        if self.is_loose() and not peek:
            self.mayloose = True
        elif not peek:
            self.mayloose = False

        # empty lines are fine:
        if Block.current_line.strip() == '':
            return True

        
        
    
        # expand tabs and get number of spaces:
        l =Block.current_line.replace('\t', '    ')
        n_space = len(l) - len(l.lstrip(' '))
        req_space = len(self.marker)
        if n_space >= req_space:
            # clean up marker:
            if not peek: Block.current_line = l[req_space:]
            self.lazy = False
            return True
        # else: we're maybe lazy
        if self.is_lazy(0): #TODO: what indent
            self.lazy = True
            return True
        # else: close
        self.open = False
        return False
    
    
    
    @staticmethod
    @overload
    def can_interrupt(b,peek=True)->str: ...
    @staticmethod
    @overload
    def can_interrupt(b,peek=False)->"List_item|None": ...

    @staticmethod
    def can_interrupt(b: Block, peek:bool=False) -> "List_item|None|str":
        '''list items can only occur in lists, but a list item existing does
        indicate that a new list can begin
        
        list items are indicated by a bullet list marker `-`, `+`, or `*`,
        or by an ordered list marker, which is a sequence of 1-9 digits followed by `.` or `)`
        
        peek means the marker is not removed from the line, and it doesn't care what b is.
        and it returns the marker (reuse for list block)
        '''
        if not type(b) == List_Block and not peek:
            return None

        # check indent:
        if Block.current_line[0:4].replace('\t','    ').strip() == '': return None # too much indent

        # count indent: 
        ind = len(Block.current_line) - len(l := Block.current_line.lstrip())

        l = l.replace('\t', '   ',1) # in case there is a tab

        # figure out the marker: (marker is followed by 1-4 spaces, if more then
        # count as no spaces and the rest is a code-block)
        if (c := l[0]) in ('-','+','*'):

            n_spaces = len(l[1:].replace('\t','    ')) - len(l[1:].replace('\t','    ').lstrip(' '))
            if l.rstrip() == c: n_spaces = 1 # empty point still counts
            if n_spaces == 0: return None # not enough spaces
            elif n_spaces > 4: n_spaces = 1 # rest is code block

            mkr = ' '* ind + c + ' ' * n_spaces

            # if in a list we must match marker
            if isinstance(b, List_Block) and (not b.marker_belongs(mkr)): return None #type: ignore
            
            if not peek: 
                Block.current_line = tab_shuffle(l[len(mkr)-ind:]) # eat line (and shuffle tabs)
                new = List_item(b,mkr) #type:ignore
                return new
            else: return mkr
            
        # match ordered list:
        ORD_MATCH = r'[0-9]{1,9}[\.\)]'
        if m:= re.match(ORD_MATCH, l):
            n_spaces = len(l[len(m[0]):]) - len(l[len(m[0]):].lstrip(' '))
            if l.rstrip() == m[0]: n_spaces = 1 # empty point still counts
            if n_spaces == 0: return None # not enough spaces
            elif n_spaces > 4: n_spaces = 1 # rest is code block
            

            mkr = ' '* ind + m[0] + ' ' * n_spaces
            
            # extra check, since only '1.' is allowed to interrupt paragraphs
            # exept if lazy continuation line (then it's a new list item)
            if isinstance(b, Paragraph) and m[0].lstrip()[:2] not in ('1)', '1.'):
                if not b.parent.lazy:
                    return None


            if not peek: 
                Block.current_line = tab_shuffle(l[len(mkr)-ind:]) # eat line (and shuffle tabs)
                new = List_item(b, mkr) #type:ignore
                return new
            else: return mkr
        return None # not ordered or unordered.


    def realize(self)->str:
        '''if parent list is "loose", paragraphs are wrapped in <p> tags, otherwise they aren't'''
        
        res = '<li>'
        for child in self.children:
            if isinstance(child, Paragraph) and not self.parent.loose: #type:ignore
                res += inline_parse(child.contents,link_references) 
            else:
                res += ('\n' if res[-1] != '\n' else '') + child.realize() + '\n'
        return res + '</li>'

class Block_quote(Block):

    def __init__(self, parent: Block | None, contents: str = "") -> None:
        super().__init__(parent, contents)

    @staticmethod
    @overload
    def can_interrupt(b,peek=True, eat=False)->bool: ...
    @staticmethod
    @overload
    def can_interrupt(b,peek=False, eat=False)->"Block_quote|None": ...

    @staticmethod
    def can_interrupt(b: Block, peek=False, eat=False) -> "Block_quote|None|bool":
        '''can a block quote go here?
        
        Block quotes defined by 0-3 indents followed by a carat: '>' and a space or tab,
         or single carat '>' followed by no space or tab
         if followed by a tab, that tab represents 3 spaces'''
        
        if not type(b) in (Block, Paragraph, List_item, Block_quote, Link_reference):
            return None
        # check indent:
        if Block.current_line[0:4].replace('\t','    ').strip() == '': return None # too much indent

        # eat whitespace, eat carat, eat ev space ( or tab)
        l = Block.current_line.lstrip(' ')
        if l[0] != '>': return None

        if l[1] == ' ':
            # one space, remove it
            l = l[2:]
        elif l[1] == '\t':
            # tab is equal to two (?) spaces, since a space and caret are included in it
            l = l.replace('\t', '  ',1)
            l = tab_shuffle(l[1:])
        else: # no space, remove caret only
            l = l[1:]
        if eat:
            Block.current_line = l # eat on can countinue

        if peek: return True
        new = Block_quote(b)
        return new
        
    
    def can_continue(self, peek=False) -> bool:
        '''if we have caret then remove it and continue, else it is lazy,
        '''
        

        if self.can_interrupt(self,peek=True, eat=True):
            self.lazy = False # not lazy
            return True
        # else: 
        self.lazy = True
        if Block.current_line.strip() == '': 
            self.open = False
            return False # empty line breaks laziness
    
        # lazy check:
        if self.is_lazy(1): # one extra space for implied '> '
            self.lazy = True
            return True
        else:
            self.open= False
            return False
    
    def realize(self) -> str:
        res = "<blockquote>\n"
        for child in self.children:
            s = child.realize()
            if s != '': # skip empty realizations
                res += s + '\n'
        return res + "</blockquote>"
   
class Fenced_code_block(Block):

    parse_verbatim:bool = True

    def __init__(self, parent: Block, delimiter:str, indent:int) -> None:
        self.delimiter = delimiter
        self.indent = indent
        # self.startline = True # get first line as well
        super().__init__(parent)

    @staticmethod
    def can_interrupt(b: Block, peek=False) -> "Fenced_code_block|None|bool":
        '''is the next a fenced code block
        
        fenced code blocks start with 0-3 indents followed by at least three of either `` ` `` or `~`,
        following the start, the next whitespace separated string is the info-string (rest of line discarded),
        after this the code block is ended by the same symbol, it may be ended on the same line (in which case there's no info string),
        if inline, the check fails and is treated in the inline part of parsing
        returns the type of delimiter if true else false'''
        
        # can only interrupt a few things:
        if not type(b) in (Block, Paragraph, List_item, Block_quote, Link_reference):
            return None
        # check indent:
        if Block.current_line[0:4].replace('\t','    ').strip() == '': return None # too much indent

        # rest of indent irrelevant:
        l = Block.current_line.lstrip(' ')
        # but needs to be counted for later:
        ind = len(Block.current_line) - len(l)


        if not ((c := l[0]) in ('`', '~')):
            return None # wrong character
        
        # count number of ticks:
        n = len(l) - len(l.lstrip(c))
        if n < 3: return None # too few
        if c == '`' and l.count(c) != n: return None # no more ticks in start
        # for tildes it's fine
        
        if peek: return True
        Block.current_line = l[n:] # remove the actual fence
        new = Fenced_code_block(b,c*n, ind)
        return new


    def can_continue(self, peek=False) -> bool:
        '''continues as long as we don't see the breaking line,
        break at least as long as start (can be longer)'''
        if not self.open: return False

        if self.parent.lazy: return False # can't continue in lazy

        l = lstrip2(Block.current_line,' ',3).rstrip()
        if l == '': return True # empty line
        if l.replace(self.delimiter[0],'') != '': return True # something else there

        if self.delimiter in l: # at least as long
            if not peek:
                Block.current_line = "" # Get rid of it from the end result
            self.open = False
            return False
        else: return True

    def add_content(self, content: str):
        self.contents += lstrip2(content, ' ', self.indent)
    
    def realize(self) -> str:

        if self.contents in ('\n', ''): return "<pre><code></code></pre>"

        s = self.contents.split('\n')
        info = sanitize_text(s.pop(0))
        
        self.contents = '\n'.join(s) # without first line and filtered
        info_s = (' class="language-' + info.split()[0] + '"') if len(info) > 0 else ""

        return "<pre><code"+ info_s + ">" + sanitize_text(self.contents, False, False, True) + "</code></pre>"

class Indented_code_block(Block):

    def can_continue(self, peek=False) -> bool:
        '''if proper indent, we can continue, blank lines can also continue'''

        if Block.current_line.strip() == '':
            # up to 4 indents should be stripped
            if not peek:
                Block.current_line = Block.current_line.replace(' ', '', 4)
            return True
        
        elif self.can_interrupt(self, peek=True):
            return True
        else: return False
    
    @staticmethod
    @overload
    def can_interrupt(b,peek=True)->bool: ...
    @staticmethod
    @overload
    def can_interrupt(b,peek=False)->"Indented_code_block|None": ...

    @staticmethod
    def can_interrupt(b: Block, peek=False) -> "Indented_code_block|None|bool":
        '''is this an indented codeblock
        indented code blocks are lines beginning with 4 indentations, followed by arbitrary text.
        Indented code blocks cannot interrupt paragraphs'''
        
        # can only interrupt a few things (notably not paragraph):
        if not type(b) in (Block, List_item, Block_quote) and not peek:
            return None
        
        if type(b) == Paragraph: return None # specifically not even if peek
        
        # otherwise it's just a question of if there's 4 or more indents
        # if tab is involved, spaces before tabs are not carried through
        st = Block.current_line[0:4] # relevant part
        if st == '    ':
            #it is good
            l = Block.current_line[4:]
        elif '\t' in st:
            # keep everything after first tab
            r,_, l = Block.current_line.partition('\t')
            if r.strip() != '': return None # things before tab
        else:
            return None
        if not peek: 
            new = Indented_code_block(b)
            return new
        else: 
            Block.current_line = l # only eat on can_continue
            return True

    def add_content(self, content: str):
        self.contents += content

    def realize(self) -> str:

        # trim empty lines: (TODO: should only trim start and end lines)
        s = self.contents.split('\n')
        while s[0] == '': s.pop(0) # inefficient but simple
        while s[-1] == '': s.pop(-1)
        l = '\n'.join(s) 

        return "<pre><code>" + replace_danger(l) + "\n</code></pre>"

one_tags = ["<pre", "<script", "<style", "<textarea"]
six_tags = ["address", "article", "aside", "base", "basefont", "blockquote", "body", "caption", "center", "col",
            "colgroup", "dd", "details", "dialog", "dir", "div", "dl", "dt", "fieldset", "figcaption", "figure",
            "footer", "form", "frame", "frameset", "h1", "h2", "h3", "h4", "h5", "h6", "head", "header", "hr",
            "html", "iframe", "legend", "li", "link", "main", "menu", "menuitem", "nav", "noframes", "ol",
            "optgroup", "option", "p", "param", "search", "section", "summary", "table", "tbody", "td", "tfoot",
            "th", "thead", "title", "tr", "track", "ul"]
six_tags.extend(['/' + s for s in six_tags]) # closing tags allowed as well
six_tags = ['<' + x for x in six_tags] # add initial bracket
six_tags.extend([s + '/' for s in six_tags]) # and extra closing /
class HTML_block(Block):
    
    def __init__(self, parent: Block, type:int) -> None:
        self.type = type
        super().__init__(parent)
        self.open = True

    @staticmethod
    def can_interrupt(b: Block, peek=False) -> "HTML_block|None|bool":
        '''does a html block start here
        
        seven conditions start and end a HTML block. this returns the number of the condition fulfilled, or 0 if not.
        contained text should be kept as is. line can also end same place it begins
        Also note! type 7 can't interrupt a paragraph'''
        if not type(b) in (Block, Paragraph, List_item, Block_quote):
            return None
        # check indent:
        if Block.current_line[0:4].replace('\t','    ').strip() == '': return None # too much indent

        l = Block.current_line.lstrip()
        t = 0

        # two: HTML comment
        if l[0:4] == "<!--":
            t = 2

        # three: PHP tag:
        elif l[0:2] == "<?":
            t = 3

        # five: CDATA:
        elif l[0:9] == "<![CDATA[":
            t = 5

        # four: other comment?
        elif l[0:2] == "<!":
            t = 4

        # one: start of area
        if t == 0: # not found yet
            for start in one_tags:
                if l.startswith(start):
                    if (len(l)>len(start) and l[len(start)] in (' ','\t','\n','>')):
                        t = 1
                        break

        
        # six: starts with regular tag
        if t == 0:
            for start in six_tags:
                if l.startswith(start):
                    if (len(l)>len(start) and l[len(start)] in (' ','\t','\n','>')) or (len(l)>len(start)+1 and l[len(start):len(start)+2] == '/>'):
                        t = 6
                        break
            else: # seven, random tag alone on line
                if isinstance(b, Paragraph): return None # 7 can't interrupt paragraph
                if not is_HTML_tag(l.rstrip()): return None # invalid tag
                else: t = 7
        # now valid start, else would have returned already
        if peek: return True
        new = HTML_block(b,t)
        return new
    
    def can_continue(self, peek=False) -> bool:
        '''7 different conditions, woah.
        If condition found add rest of line verbatim'''
        if not self.open: return False # already closed

        if self.type == 1: # closing tag
            for sub in ["</pre>", "</script>", "</style>", "</textarea>"]:
                if sub in Block.current_line.lower():
                    # it's the last line:
                    self.open = False
                    return True
        
        elif self.type == 2:
            if "-->" in Block.current_line:
                # it's the last line:
                self.open = False
                return True
        
        elif self.type == 3:
            if "?>" in Block.current_line:
                # it's the last line:
                self.open = False
                return True
                    
        elif self.type == 4:
            if "!>" in Block.current_line:
                # it's the last line:
                self.open = False
                return True
        
        elif self.type == 5:
            if "]]>" in Block.current_line:
                # it's the last line:
                self.open = False
                return True
        elif self.type >= 6: # six or seven
            if Block.current_line.strip() == '':
                self.open = False
                return False # no need to add empty line
        
        return True # if not stopped keep on reading
        
    def add_content(self, content: str):
        self.contents += content
    
    def realize(self) -> str:
        return self.contents.rstrip('\n') # edge case

link_references= [] # references have: label, link, and title (clean before use)
class Link_reference(Block):

    link_instances:list["Link_reference"] = []

    def __init__(self, parent: Block | None, contents: str = "") -> None:
        self.startline = True
        self.link_instances.append(self)
        self.evaluated = False
        super().__init__(parent, contents)

    def can_continue(self, peek=False) -> int:

        if self.startline: # to ensure it can continue on the first line
            self.startline = False
            return True
        if not self.open: return False

        for t in (Fenced_code_block,Setext_heading,Block_quote,List_Block,ATX_heading): # preempt interruption, to close correctly
                # don't know which, TODO
                if t.can_interrupt(self, peek=True):
                    self.open = False
                    self.evaluate_ref()
                    return False
        if self.can_interrupt(self, peek=True): # new link takes precedence
            self.open = False
            self.evaluate_ref()
            return False
        if not Block.current_line.strip() == "": return True # other non-empty line we can continue on
        #else:
        self.evaluate_ref()
        self.open = False
        return False
    
    @staticmethod
    def can_interrupt(b: Block, peek:bool=False) -> "Link_reference|None|bool":
        '''is this a link reference
        
        link references are comprised of a link label preceeded by 0-3 indentation
        then a colon `:`, then (with optional whitespace including up to one line break)
        a link destination, then (at least one whitespace)
        an optional link title. and no further elements.
        
        plan is to treat a potential link reference as link reference, then regress to paragraph is not
        (link reference also cannot interrupt a paragraph)'''

        if not peek and not type(b) in (Block, List_item, Block_quote):
            return None
        # check indent:
        if Block.current_line[0:4].replace('\t','    ').strip() == '': return None # too much indent

        # early parsing:
        l = Block.current_line.lstrip()
        if l[0] != '[': return None
        label,_,rest = l[1:].partition(']') # rest may be empty if title continues
        if len(label.lstrip())>0 and (not valid_label_name(label)): return None

        if not peek:
            new = Link_reference(b)
            return new
        else: return True


    def add_content(self, content: str):
        self.contents += content

    @staticmethod
    def evaluate_all():
        '''Evaluates and then deletes all link references'''
        for b in Link_reference.link_instances:
            b.evaluate_ref()
        
        Link_reference.link_instances = [] # reset

    
    def evaluate_ref(self):
        '''check if link reference is valid, if it is, add to list of references, else
        regress to paragraph.'''
        if self.evaluated: return;
        self.evaluated = True

        if (t :=self.isvalid()):
            link_references.append({
                "label": label_collapse(t[0]), # type:ignore
                "dest": t[1], # type:ignore
                "title": t[2] # type:ignore
            })
            self.open = False # close yourself
        else:
            # revert to paragraph (create paragraph, give it contents, kill self)
            # parent already has?
            self_idx = self.parent.children.index(self)
            if self_idx > 0: pot = self.parent.children[self_idx-1] # one before us
            else: pot = None
            if isinstance(pot,Paragraph) and pot.open:
                p = pot
            else: # nope, make new
                p = Paragraph(self.parent)
                # reshuffle to put p in right place (open_child might be wrong but oh well)
                self.parent.children.remove(p)
                self.parent.children.insert(self_idx+1, p)
            p.contents += self.contents
            self.parent.children.remove(self) # orphan yourself
            p.can_continue() # check if p should be open
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
        if len(cont) == 0 or cont[0] != '[': return False
                
        # find unescaped `]`:
        if (m := re.search(UNESCAPED_BRACE, cont)) is None: return False # no close, invalid
        # split on the unescaped brace:
        label = cont[1:m.end()-1]
        rest = cont[m.end():]
        label = label.strip('\n') # in case we wrote over multiple lines
        



        if not valid_label_name(label): return False

        # check for colon:
        if not rest[0] == ':': return False
        else: rest = rest[1:] # remove colon

        # now rest has destination and title.
        # TODO: this could be simpler since a space is required between destination and title

        rest = rest.lstrip() # remove whitespace
        if len(rest) < 2: return False # need some kind of link, even if empty
        if rest[0] == '<':
            # braced destination
            # find unescaped `>`
            m = re.search(UNESCAPED_ANG_BRACE,rest)
            if m is None: return False # no closing `>`
            # else:
            dest = rest[1:m.end()-1]
            title = rest[m.end():]
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
            title = rest[len(dest):]

        if len(title) > 0 and (not title[0] in (' ', '\t', '\n')):return False # need whitespace separation

        if not valid_link_title(title.strip()):
            
            # if title is on it's own line, then perhaps it's not a title at all
            if title.replace('\t','').strip(' ')[0] != '\n': return False # nope that's just false
            # move "title" to next paragraph and try again

            p = Paragraph(self.parent) # new paragraph
            p.contents = title
            self.contents = self.contents.replace(title,'') # remove title

            return self.isvalid() # recurse
        # finally if nothing shouted false, return values
        return label, dest, title.strip()[1:-1] # title trimmed of containers
    
    def realize(self) -> str:
        if self.open: self.evaluate_ref() # just in case we're last
        return '' # link references aren't printed

class Paragraph(Block):
    
    def can_continue(self, peek= False) -> bool:
        if not self.open: return False
        if not Block.current_line.strip() == "": return True
        self.open = False # can't have whitespace
        return False

    def add_content(self, content: str):
        self.contents += content

    @staticmethod
    def can_interrupt(b: Block, peek=False) -> None:
        return None # paragraph can't interrupt, but get created when
        # things are added to container blocks

    def realize(self) -> str: # strip 0 to 3 spaces before
        return "<p>" + inline_parse(self.contents, link_references) + "</p>"

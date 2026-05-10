# ob.md-to-html
A script for parsing obsidian markdown into HTML. Based on the Github Flavoured Markdown spec, and CommonMarc spec

All of CommonMark is supported.
The following extras will be supported:
([] test added, [] tests cleared)
- [x][x] tables
- [x][x] task list items
- [x][x] strikethrough (& highlight)
    note: unlike GFM, strike and highlight are 2 indicators, and more will be included after the indicator (OB a bit inconsistent)
- [x][x] autolink extension
    this means that CM example 608,611, and 612 are invalid (so were removed)
    GFM test 624 i disagree with, so it's excluded as well
- [x][x] wikilinks (with alias and paragraph linking)
    to implement this, the preprocessor should add all wikilinks as link-labels before parsing
    it should also make link-labels for all headings to allow heading linking.
    finally wikiformat should recognize `|` as a custom name indicator.
    a duplicate of all labels with .md added should also be added to comply with regular markdown formatted links.
- [][x] wiki-like embedded images
    embedded images should see `|` to specify width and height
- [][] footnotes
- [x][x] callouts
- [x][x] comments
    inline comments and block comments are replaced by their HTML counterparts,
    inline is indicated by `%%` and block is indicated by `%%\n`. they are replaced by `<!--` and `-->`
- [x][x] LaTeX snippets (via mathjax)
    Unlike pure MathJax, OB only starts inline math when $ not followed by whitespace, and only ends it when not preceded by whitespace
    To not have false positives as well, the indicators for starting and ending math should be changed, (and set in MathJax on the HTML side) 
- [][] mermaid diagrams?

not done:
- block definitions (never use them)
- embedding of entire notes, pdfs, audio, or anything other than image
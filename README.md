# ob.md-to-html
A script for parsing obsidian markdown into HTML. Based on the Github Flavoured Markdown spec, and CommonMarc spec

All of CommonMark is supported.
The following extras will be supported:
[] test added, [] tests cleared
- [x][] tables
- [x][] task list items
- [x][] strikethrough (& highlight)
    note: unlike GFM, strike and highlight are 2 or more indicators, not 1 or 2!
- [x][] autolink extension
    this means that CM example 608,611, and 612 are invalid
- [][] wikilinks (with alias and paragraph linking)
- [][] block definitions (?)
- [][] footnotes
- [][] callouts
- [][] comments
- [][] LaTeX snippets (via mathjax)


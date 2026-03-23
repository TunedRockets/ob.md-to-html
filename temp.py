import re


s = "<blablabla\>bla bla bnla>"

m = re.search(r"(?<!\\)[>]", s)
print(m)
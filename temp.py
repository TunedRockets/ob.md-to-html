import re


PATTERN = r'(^|[ac])b'

string = 'b ab cb dbb'
for m in re.finditer(PATTERN, string):
    print("match:", m, m.start())
import re


s = "ö"

i = s.encode()
for b in i:
    print(f'{b:X}')
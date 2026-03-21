import re
s = ""
NAME_PATTERN = r"[abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ01234567890-]+"
if re.fullmatch(NAME_PATTERN, s):
    print('yes')
else:
    print('no')
import glob
import re

for p in glob.glob('toolkit/dev/input/lab/*.json'):
    text = open(p, encoding='utf-8').read()
    if 'Sample received from' in text:
        m = re.search(r"Sample received from\s+([^,\n\)]+)", text)
        print(p, m.group(0) if m else '')

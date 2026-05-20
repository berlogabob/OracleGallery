from pathlib import Path
import re

typ = Path("reports/neje_audit_report.typ")
txt = typ.read_text()

fixed = {}

# All known broken patterns → correct rgb("#NNNNNN")
broken = [
    'rgb(rgb("#1a1a1a"))',
    'rgb(rgb("#0d0d0d"))',
    'rgb(rgb("#888888"))',
    'rgb(rgb("#f5f1eb"))',
    'rgb(rgb("#fff8e8"))',
    'rgb(rgb("#eaf4ff"))',
    'rgb(rgb("#b8860b"))',
    'rgb(rgb("#8f8980"))',
    'rgb(rgb("#1f1a17"))',
]

for pat in broken:
    m = re.search(r'"([0-9a-fA-F]{6})"', pat)
    if m:
        correct = 'rgb("' + m.group(1) + '")'
        if pat in txt:
            txt = txt.replace(pat, correct)
            fixed[pat] = correct
        elif correct in txt:
            print('  already correct:', correct)
        else:
            print('  NOT FOUND (already maybe correct):', pat[:40])

print('fixed patterns:', len(fixed))

# Show lines with the remaining issues
all_remaining = []
for i, line in enumerate(txt.splitlines(), 1):
    if 'rgb("#' in line:
        all_remaining.append((i, line))

print('lines with rgb("...):', len(all_remaining))
for i, line in all_remaining[:10]:
    print(f'  L{i}: {line[:120]}')

typ.write_text(txt)
print('done')

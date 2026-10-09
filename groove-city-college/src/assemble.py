import sys, os
here = os.path.dirname(os.path.abspath(__file__))
tpl = open(os.path.join(here, 'template.html'), encoding='utf-8').read()
data = open(sys.argv[1], encoding='utf-8').read()
page = tpl.replace('/*__DATA__*/', data)
# fragment for publishing as an Artifact (the host adds doctype/head/body)
open(os.path.join(here, '..', 'artifact.html'), 'w', encoding='utf-8').write(page)
# complete document for opening locally
head = ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n')
full = head + page.replace('<canvas id="view">', '</head><body>\n<canvas id="view">', 1) + '\n</body></html>\n'
out = os.path.join(here, '..', 'index.html')
open(out, 'w', encoding='utf-8').write(full)
print('wrote', os.path.normpath(out), os.path.getsize(out), 'bytes')

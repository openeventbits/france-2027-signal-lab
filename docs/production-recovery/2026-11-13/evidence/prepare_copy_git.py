"""Give disposable validation copies read-only access to authenticated Git objects.

Each copy has its own HEAD/config/index. No commits or refs are created, and no
production index or working tree is reused. Tests can run git show/ls-files.
"""
import os, subprocess, sys
from pathlib import Path
ev=Path(__file__).resolve().parent
original=Path('C:/Users/Tanya/Documents/GitHub/france-2027-signal-lab')
objects=(original/'.git/objects').as_posix()
for name in sys.argv[1:]:
    root=ev/'validation'/name
    if not root.is_dir(): raise ValueError(root)
    if (root/'.git').exists() and (root/'.git/HEAD').read_text().strip() != 'caada6984cdb4719ac2cab5310c4d27b5ac7d093':
        raise ValueError('unexpected metadata')
    subprocess.run(['git','init','--quiet',str(root)],check=True)
    (root/'.git/objects/info/alternates').write_bytes((objects+'\n').encode('utf-8'))
    (root/'.git/HEAD').write_bytes(b'caada6984cdb4719ac2cab5310c4d27b5ac7d093\n')
    subprocess.run(['git','-c',f'safe.directory={root.as_posix()}','-C',str(root),'read-tree','HEAD'],check=True)
    print(name,'independent index at authenticated main',flush=True)

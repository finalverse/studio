import sys
from PIL import Image
out=sys.argv[1]; files=sys.argv[2:]; h=int(__import__('os').environ.get('MH','700'))
ims=[Image.open(f).convert('RGB') for f in files]
ims=[i.resize((int(i.width*h/i.height),h)) for i in ims]
W=sum(i.width for i in ims); m=Image.new('RGB',(W,h)); x=0
for i in ims: m.paste(i,(x,0)); x+=i.width
m.save(out)

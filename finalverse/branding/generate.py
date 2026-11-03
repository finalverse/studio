# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Original code/vector branding; no upstream logo or third-party artwork."""
from pathlib import Path
import math
import subprocess
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parent
svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><g fill="none" stroke="currentColor" stroke-width="8" stroke-linecap="round"><path d="M96 92A44 44 0 1 1 104 43"/><path d="M49 91V38h34M49 62h27"/><path d="m94 20 16 17-22 4"/></g></svg>'''
(root/'mark.svg').write_text(svg)
for p in ['release/datafiles/icons_svg/blender.svg','release/datafiles/icons_svg/blender_logo_large.svg']:
    # Blender's native icon rasterizer uses a fixed 1600-unit glyph canvas.
    glyph_svg = svg.replace('viewBox=', 'width="1600" height="1600" viewBox=')
    (root.parents[1]/p).write_text(glyph_svg.replace('currentColor', '#fff'))


def mark(draw, x, y, size, color, width):
    box=[x+size*.15,y+size*.15,x+size*.85,y+size*.85]
    draw.arc(box,42,327,fill=color,width=width)
    points=[(x+size*.39,y+size*.71),(x+size*.39,y+size*.30),(x+size*.65,y+size*.30)]
    draw.line(points, fill=color, width=width,joint='curve')
    draw.line([(x+size*.39,y+size*.49),(x+size*.59,y+size*.49)],fill=color,width=width)
    draw.polygon([(x+size*.75,y+size*.15),(x+size*.88,y+size*.29),(x+size*.69,y+size*.32)], fill=color)


im=Image.new('RGBA',(2048,2048),(0,0,0,0));d=ImageDraw.Draw(im)
d.rounded_rectangle([32,32,2016,2016],radius=430,fill='#0c1525')
d.rounded_rectangle([50,50,1998,1998],radius=420,outline='#2a3f51',width=7)
mark(d,190,190,1668,'#f2ce89',100)
im=im.resize((1024,1024),Image.Resampling.LANCZOS);im.save(root/'icon.png')
icons=root/'finalverse-studio.iconset';icons.mkdir(exist_ok=True)
for size in [16,32,128,256,512]:
 for scale in [1,2]:
  name=f'icon_{size}x{size}'+('@2x' if scale==2 else '')+'.png'
  im.resize((size*scale,size*scale),Image.Resampling.LANCZOS).save(icons/name)
subprocess.run(['/usr/bin/iconutil','-c','icns',str(icons),'-o',str(root/'finalverse-studio.icns')],check=True)
# Fully authored splash with a restrained orbit motif, not a generated UI screenshot.
im=Image.new('RGB',(1600,800),'#0c1525');d=ImageDraw.Draw(im)
for radius in range(700,1100,70):
 d.arc([1040-radius,400-radius,1040+radius,400+radius],105,250,fill='#172c3c',width=2)
mark(d,980,130,520,'#f2ce89',24)
font='/System/Library/Fonts/Supplemental/Arial.ttf'
bold='/System/Library/Fonts/Supplemental/Arial Bold.ttf'
d.text((110,170),'FINALVERSE',font=ImageFont.truetype(bold,78),fill='#f2ce89')
d.text((110,265),'STUDIO',font=ImageFont.truetype(font,128),fill='#eef5f7')
d.line([(115,442),(450,442)],fill='#4eabaf',width=5)
d.text((115,490),'Create. Animate. Author worlds.',font=ImageFont.truetype(font,31),fill='#b7c8ce')
d.text((115,690),'Based on Blender  ·  Open source  ·  S0 development',font=ImageFont.truetype(font,22),fill='#93a8b4')
im.save(root/'splash.png');im.save(root.parents[1]/'release/datafiles/splash.png')

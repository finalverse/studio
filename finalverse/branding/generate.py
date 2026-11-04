# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Studio identity derived from the user's approved white Finalverse emblem."""
from pathlib import Path
import json
import subprocess
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parent
# Simplified vector outlines of Finalverse_logo_07; retain the angular silhouette
# and its four separated pieces instead of the provisional S0 portal/F design.
polygons = [
    [(89,70),(133,70),(74,162),(52,128)],
    [(227,70),(271,70),(308,128),(286,162)],
    [(158,70),(202,70),(237,124),(178,215),(156,181),(193,124),
     (180,104),(130,183),(200,291),(178,326),(86,182)],
    [(250,146),(272,180),(214,270),(192,236)],
]
shapes = ''.join('<polygon points="' + ' '.join(f'{x},{y}' for x,y in p) + '"/>' for p in polygons)
svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 360"><g fill="#fff">{shapes}</g></svg>'
(root/'mark.svg').write_text(svg)
for p in ['release/datafiles/icons_svg/blender.svg','release/datafiles/icons_svg/blender_logo_large.svg']:
    # Blender's native icon rasterizer uses a fixed 1600-unit glyph canvas.
    glyph_svg = svg.replace('viewBox=', 'width="1600" height="1600" viewBox=')
    (root.parents[1]/p).write_text(glyph_svg)
for p in ['release/freedesktop/icons/scalable/apps/blender.svg',
          'release/freedesktop/icons/symbolic/apps/blender-symbolic.svg']:
    (root.parents[1]/p).write_text(svg)

(root/'logo-white.svg').write_text(
    '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="360" viewBox="0 0 1200 360">'
    f'<g fill="#fff">{shapes}</g>'
    '<g fill="#fff" font-family="Arial, sans-serif">'
    '<text x="390" y="175" font-size="104" font-weight="700">Finalverse</text>'
    '<text x="396" y="258" font-size="46" letter-spacing="18">STUDIO</text>'
    '</g></svg>')


def mark(draw, x, y, size, color='#ffffff'):
    for polygon in polygons:
        draw.polygon([(x+px/360*size,y+py/360*size) for px,py in polygon],fill=color)


font='/System/Library/Fonts/Supplemental/Arial.ttf'
bold='/System/Library/Fonts/Supplemental/Arial Bold.ttf'


def tracking(draw, xy, text, size, gap, fill):
    x,y=xy;face=ImageFont.truetype(font,size)
    for letter in text:
        draw.text((x,y),letter,font=face,fill=fill)
        x+=draw.textlength(letter,font=face)+gap


logo=Image.new('RGBA',(2400,720),(0,0,0,0));d=ImageDraw.Draw(logo)
mark(d,0,0,720)
d.text((780,130),'Finalverse',font=ImageFont.truetype(bold,208),fill='#ffffff')
tracking(d,(792,426),'STUDIO',92,36,'#ffffff')
logo=logo.resize((1200,360),Image.Resampling.LANCZOS);logo.save(root/'logo-white.png')
preview=Image.new('RGBA',logo.size,'#101020');preview.alpha_composite(logo)
preview.convert('RGB').save(root/'logo-preview.png')


im=Image.new('RGBA',(2048,2048),(0,0,0,0));d=ImageDraw.Draw(im)
d.rounded_rectangle([32,32,2016,2016],radius=430,fill='#101020')
d.rounded_rectangle([50,50,1998,1998],radius=420,outline='#4d3e6b',width=7)
mark(d,-82,-140,2212)
im=im.resize((1024,1024),Image.Resampling.LANCZOS);im.save(root/'icon.png')
icons=root/'finalverse-studio.iconset';icons.mkdir(exist_ok=True)
for size in [16,32,128,256,512]:
 for scale in [1,2]:
  name=f'icon_{size}x{size}'+('@2x' if scale==2 else '')+'.png'
  im.resize((size*scale,size*scale),Image.Resampling.LANCZOS).save(icons/name)
subprocess.run(['/usr/bin/iconutil','-c','icns',str(icons),'-o',str(root/'finalverse-studio.icns')],check=True)
# Vector composition; no generated world imagery or claims about rendering quality.
im=Image.new('RGB',(1600,800),'#0b0d19');d=ImageDraw.Draw(im)
for offset in [0,48,96]:
 d.line([(1030+offset,0),(1550+offset,800)],fill='#1d1832',width=2)
mark(d,960,100,570)
d.text((110,182),'Finalverse',font=ImageFont.truetype(bold,108),fill='#ffffff')
tracking(d,(117,324),'STUDIO',66,24,'#ffffff')
d.line([(117,450),(445,450)],fill='#ad98ed',width=5)
d.text((117,500),'Create. Animate. Author worlds.',font=ImageFont.truetype(font,31),fill='#c0bfd5')
stage=json.loads((root.parent/'product.json').read_text())['stage']
d.text((117,690),'Based on Blender  ·  Open source  ·  '+stage,font=ImageFont.truetype(font,22),fill='#9b9bb4')
im.save(root/'splash.png');im.save(root.parents[1]/'release/datafiles/splash.png')

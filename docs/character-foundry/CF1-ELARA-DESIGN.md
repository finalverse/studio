# CF1: Elara Vayne design brief (v1)

**Canon (Core E1):** identity `Elara`, human, `height_mm` 1720. Clothing,
skin and hair palette fields in the E1 spec. **Canonical reference:** the owner's
vision art `elara-vision.png` (2026-11-07). Where the E1 palette fields and the
vision art differ, the vision art wins for look and the E1 identity, height and
body type stay fixed.

## Identity in one line

A young explorer-musician of the wild places: warm, curious, at ease outdoors.
She reads as practical, not armoured, and storybook rather than gritty.

## Silhouette (what must survive at 18 m)

1. **Cloak triangle.** A deep-blue hooded cloak falls from the shoulders to
   mid-calf and opens at the front. The hood lies folded on the upper back.
2. **Braid line.** A thick auburn braid runs from behind her left ear over the
   left shoulder down the chest. It is the asymmetric accent.
3. **Belted tunic.** The forest-green tunic is cinched at the waist and ends at
   mid-thigh. Half sleeves end just below the elbow with rolled cuffs.
4. **Crossbody line.** A leather strap runs from her right shoulder to a satchel
   at her left hip, with a wooden flute tucked along it.
5. **Tall boots.** Brown laced boots reach mid-calf with folded cuffs.

## Layers and materials

| Layer | Form | Material intent |
| --- | --- | --- |
| Skin | MakeHuman hm08, young adult female, ideal proportions, slightly lean | warm fair (`#e9bba0`), cheek and nose blush, light freckles over the nose bridge, subsurface |
| Face | eyes 8% larger than anatomical (gentle stylisation), arched tapered brows, soft lips | hazel-green iris with limbal ring, wet cornea (coat), dark-auburn brows, rose lips |
| Hair | centre part, pulled back over the ears into the braid; loose temple strands frame the face | auburn `#6a2914` → highlights `#a64c25`, darker roots, anisotropic sheen |
| Tunic | belted, slight A-line, scoop neck | woven green linen `#47693a`, **gold embroidery**: music staff with notes on the hem, scrolling vine on the placket and hem band, leaf trim at the neckline |
| Leggings | fitted | olive-brown knit `#4c3b24` |
| Belt, strap, satchel | 38 mm belt with brass buckle; 34 mm strap; satchel with domed flap and buckle strap | brown leather `#6e4527` with grain, darkened edges and pale stitching |
| Flute | end-blown, three ferrules, six finger holes | warm wood with lacquer |
| Cloak | wool, cloth-draped, lining visible at the opening | deep blue `#2c4b73` wool with twill, **gold leaf border** at the hem and front edges, scattered leaves on the shoulders; navy lining `#1b2742` with a gold leaf frieze |
| Clasp | orange flower brooch at her left collarbone | `#e2782a` with soft subsurface |
| Boots | tall, laced, folded cuff, flat sole | leather, cuff and sole in the same family |

## Palette discipline

Three dominant hues only: green (tunic), blue (cloak) and auburn/brown (hair,
leather, leggings). Gold is the single accent metal and thread. Saturation
peaks in the hair and the embroidery, so the face and the gold read first.

## Shared visual language for the founders (house style)

- Anatomical or archetype-correct base forms. No primitive assemblies.
- Painted PBR: a readable albedo design with real micro-normal and roughness
  variation. Avoid flat factors as the final look.
- One accent material per character (Elara: gold thread; Kai: gold plate with
  amber light; Ignis: molten seams; Terra: amber eyes and heart; Lumi:
  teal eyes; Melody: bioluminescent dots).
- Eyes are the focal point at the focus camera: large irises, a catch light
  (coat) and clear lids.
- Two-rig evidence: the neutral rig with Infinity's tone mapper, and a dusk
  production rig after the vision art.

## Do / don't

- **Do** keep the braid over the *left* shoulder and the satchel on the *left* hip, as in the vision art.
- **Do** keep the cloak open at the front so the tunic embroidery reads.
- **Don't** add armour, weapons or a hood worn up. She is an explorer, not a ranger-warrior.
- **Don't** let the cloak swallow her silhouette from behind. The hood and the gold hem carry the rear view.

## Out of scope for v1 (noted for v2)

- The hummingbird companions and glowing flora of the vision art are environment
  and companion assets, not part of the character.
- Hair is modelled as sculpted locks, not strands (see toolchain notes).

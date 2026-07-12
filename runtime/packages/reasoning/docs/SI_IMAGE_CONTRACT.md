# SI Image Contract

## Stock of truth
- **Scene graph + scene plan** are the workpiece.
- **PNG** is a camera readout after construct / view / ISP / optional picture-edit.

## Construction modes
| Mode | Meaning |
|------|---------|
| native | SHAPES tokens only |
| mapped | synonyms → known entities |
| composite | puzzle pieces from roles |
| mill | CNC contour/pocket paths |
| lathe | solid of revolution |
| extrude | print-lite box/stack volume |
| mixed | combination |
| retrieved | real media (not SI) |
| picture_edit | post-raster grade/text |

## Pass order
1. Construct (mill / lathe / extrude / composite)
2. View (yaw / pitch / time)
3. ISP (camera look)
4. Picture-edit (grade / text) — does not add world entities

## Non-goals
- Diffusion / generative fill as SI
- Claiming photoreal identity from composites
- Treating PNG alone as editable 3D stock

"""Visual checks for authored sprite placement; no geometry is inferred."""
import math
from PIL import Image, ImageDraw, ImageOps


def registration_sheet(frames, *, anchor=(0.5, 1.0), labels=None,
                       collision_box=None, attachments=None, mirror=False,
                       scale=4, columns=3, background="#ededee"):
    """Inspect selected final frames at one pivot with authored gameplay geometry.

    Returns a PIL image, not a package cover. Frames are PIL images on one shared
    canvas. Pick representative states (including the firing pose), label them,
    and supply frame-pixel collision_box={x,y,w,h} and attachments={name:{x,y}}.
    mirror=True adds reflected copies around the same pivot. No pixels are fixed
    and no body/weapon locations are guessed. Use light and dark backgrounds.
    """
    frames = list(frames)
    if not frames or len({f.size for f in frames}) != 1:
        raise ValueError("Choose nonempty final frames on one shared canvas")
    if not isinstance(scale, int) or not 1 <= scale <= 8 or not isinstance(columns, int) or not 1 <= columns <= 8:
        raise ValueError("scale and columns must be integers from 1 to 8")
    if len(anchor) != 2 or any(not math.isfinite(v) or not 0 <= v <= 1 for v in anchor):
        raise ValueError("anchor uses two normalized coordinates from the top-left")
    labels = list(labels) if labels is not None else [str(i) for i in range(len(frames))]
    if len(labels) != len(frames):
        raise ValueError("Supply one label per frame")
    w, h = frames[0].size
    ax, ay = anchor[0]*w, anchor[1]*h
    margin, header = 20, 28
    cw, ch = math.ceil(2*max(ax,w-ax)*scale)+margin*2, h*scale+margin*2+22
    samples = [(f,label,face) for f,label in zip(frames,labels) for face in ([1,-1] if mirror else [1])]
    columns = min(columns,len(samples))
    if columns*cw*math.ceil(len(samples)/columns)*ch > 32*1024*1024:
        raise ValueError("Review sheet is too large; select fewer representative frames")
    out=Image.new("RGBA",(columns*cw,header+math.ceil(len(samples)/columns)*ch),background)
    draw=ImageDraw.Draw(out)
    rgb=out.getpixel((0,0));text="#ededee" if sum(rgb[:3])<380 else "#252528"
    draw.text((8,8),"Orange: collision  |  Cyan: attachments  |  Magenta: pivot",fill=text)
    for i,(frame,label,face) in enumerate(samples):
        x,y=(i%columns)*cw,header+(i//columns)*ch
        px,py=x+cw/2,y+margin+ay*scale
        origin=px-(ax if face==1 else w-ax)*scale
        im=frame.convert("RGBA")
        if face==-1:im=ImageOps.mirror(im)
        out.alpha_composite(im.resize((w*scale,h*scale),Image.Resampling.NEAREST),(round(origin),y+margin))
        draw.line((x+5,py,x+cw-5,py),fill="#929299")
        if collision_box:
            b=collision_box
            left=px+((b['x']-ax) if face==1 else ax-b['x']-b['w'])*scale
            top=py+(b['y']-ay)*scale
            draw.rectangle((left,top,left+b['w']*scale,top+b['h']*scale),outline="#e87832",width=2)
        for name,p in (attachments or {}).items():
            dx,dy=px+face*(p['x']-ax)*scale,py+(p['y']-ay)*scale
            draw.ellipse((dx-3,dy-3,dx+3,dy+3),fill="#008fba")
            draw.text((dx+5,dy-10),str(name),fill=text)
        draw.line((px-5,py,px+5,py),fill="#df2c9a",width=2)
        draw.line((px,py-5,px,py+5),fill="#df2c9a",width=2)
        draw.text((x+8,y+ch-17),str(label)+(" / mirrored" if face==-1 else ""),fill=text)
    return out.convert("RGB")

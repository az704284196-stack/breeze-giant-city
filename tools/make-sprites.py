# -*- coding: utf-8 -*-
"""从创作设定图里抠出三视图与特写，直接作为游戏贴图（不改动造型）"""
from PIL import Image, ImageDraw
import numpy as np

SRC = 'assets/breeze-sheet.png'
im = Image.open(SRC).convert('RGB')
W, H = im.size
a = np.asarray(im).astype(np.int16)
print('size', W, H)

# --- 背景色（边框取样） ---
border = np.concatenate([
    a[0:8, :].reshape(-1, 3), a[-8:, :].reshape(-1, 3),
    a[:, 0:8].reshape(-1, 3), a[:, -8:].reshape(-1, 3)])
bg = np.median(border, axis=0)
print('bg', bg)

d = np.abs(a - bg).sum(axis=2)                 # 与背景色的曼哈顿距离

# --- 只保留与画布边缘连通的背景（避免误伤角色内部的浅色） ---
bglike = d < 60
conn = np.zeros_like(bglike)
conn[0, :] |= bglike[0, :]; conn[-1, :] |= bglike[-1, :]
conn[:, 0] |= bglike[:, 0]; conn[:, -1] |= bglike[:, -1]
for it in range(4000):
    nxt = conn.copy()
    nxt[1:, :] |= conn[:-1, :]; nxt[:-1, :] |= conn[1:, :]
    nxt[:, 1:] |= conn[:, :-1]; nxt[:, :-1] |= conn[:, 1:]
    nxt &= bglike
    if nxt.sum() == conn.sum():
        break
    conn = nxt
print('flood iters', it, 'bg px', int(conn.sum()))

# --- 软化边缘：alpha 随距离渐变，仅作用于背景连通区 ---
alpha = np.full((H, W), 255, dtype=np.float32)
ramp = np.clip((d - 26) / 46.0, 0.0, 1.0) * 255.0
alpha[conn] = ramp[conn]
alpha = np.clip(alpha, 0, 255).astype(np.uint8)
rgba = np.dstack([np.asarray(im), alpha])
full = Image.fromarray(rgba, 'RGBA')

fg = alpha > 12


def runs(proj, min_len, gap):
    out, start = [], None
    for i, v in enumerate(proj):
        if v > min_len:
            if start is None:
                start = i
        else:
            if start is not None:
                out.append((start, i))
                start = None
    if start is not None:
        out.append((start, len(proj)))
    merged = []
    for r in out:
        if merged and r[0] - merged[-1][1] < gap:
            merged[-1] = (merged[-1][0], r[1])
        else:
            merged.append(list(r) if False else (r[0], r[1]))
    return [m for m in merged if m[1] - m[0] > min_len]


def bbox_from(mask):
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def main_band(mask, min_len=3, gap=24):
    """取前景像素最多的那条竖向条带，避免把底部图注文字一起框进来"""
    proj = mask.sum(axis=1)
    best, best_w = None, -1
    for (y0, y1) in runs(proj, min_len, gap):
        w = int(proj[y0:y1].sum())
        if w > best_w:
            best, best_w = (y0, y1), w
    return best


def largest_component(mask):
    """从前景最密处泛洪，只保留与主体连通的部分（清掉残留图注/碎点）"""
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return mask
    # 种子：取前景最密的行里最靠中间的点
    row = int(np.argmax(mask.sum(axis=1)))
    cols = np.where(mask[row])[0]
    seed = (row, int(cols[len(cols) // 2]))
    cur = np.zeros_like(mask)
    cur[seed] = True
    for _ in range(4000):
        nxt = cur.copy()
        nxt[1:, :] |= cur[:-1, :]; nxt[:-1, :] |= cur[1:, :]
        nxt[:, 1:] |= cur[:, :-1]; nxt[:, :-1] |= cur[:, 1:]
        nxt &= mask
        if nxt.sum() == cur.sum():
            break
        cur = nxt
    return cur


# --- 左侧三视图 ---
left = fg[:, :int(W * 0.80)]
colproj = left.sum(axis=0)
boxes = []
for (x0, x1) in runs(colproj, 4, 18):
    # 若一块区域内投影上粘连了多个视图（宽 > 高），在中间最窄处再切一刀
    if (x1 - x0) > 620:
        lo, hi = x0 + int((x1 - x0) * 0.40), x0 + int((x1 - x0) * 0.70)
        cut = lo + int(np.argmin(colproj[lo:hi]))
        parts = [(x0, cut), (cut, x1)]
    else:
        parts = [(x0, x1)]
    for (px0, px1) in parts:
        sub = fg[:, px0:px1]
        rr = main_band(sub)
        if not rr:
            continue
        y0, y1 = rr
        # 收紧到真实内容边界
        bb = bbox_from(fg[y0:y1, px0:px1])
        if bb is None:
            continue
        boxes.append((px0 + bb[0], y0 + bb[1], px0 + bb[2], y0 + bb[3]))
print('view boxes:', boxes)

def clean_alpha(crop):
    """只保留主体连通块，去掉残留图注与孤立碎点，再按内容紧裁"""
    arr = np.asarray(crop).copy()
    if arr.ndim == 2:
        return crop
    keep = largest_component(arr[:, :, 3] > 12)
    arr[:, :, 3] = np.where(keep, arr[:, :, 3], 0).astype(np.uint8)
    out = Image.fromarray(arr, 'RGBA')
    bb = bbox_from(np.asarray(out)[:, :, 3] > 12)
    return out.crop(bb) if bb else out


names = ['front', 'side', 'back']
for i, b in enumerate(boxes[:3]):
    pad = 4
    x0, y0, x1, y1 = b
    crop = full.crop((max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad)))
    # 再按内容紧裁一次
    bb = bbox_from(np.asarray(crop)[:, :, 3] > 12)
    if bb:
        crop = crop.crop(bb)
    crop = clean_alpha(crop)
    crop.save('assets/breeze-%s.png' % names[i])
    print('saved assets/breeze-%s.png' % names[i], crop.size)

# --- 右侧特写 ---
right = fg[:, int(W * 0.80):]
cands = []
for (y0, y1) in runs(right.sum(axis=1), 6, 20):
    sub = right[y0:y1, :]
    band = main_band(sub, 6, 10)
    if band and (y1 - y0) > 40:
        by0, by1 = y0 + band[0], y0 + band[1]
        bb = bbox_from(right[by0:by1, :])
        cands.append((by0, by1, bb))
print('right boxes:', [(c[0], c[1], c[2]) for c in cands])

cands_sorted = sorted(cands, key=lambda c: c[0])
# 最下方三块 = 舌头 / 肉垫 / 额头（自上而下）
picked = cands_sorted[-3:] if len(cands_sorted) >= 3 else cands_sorted
labels = ['face', 'paw', 'mouth']
if len(picked) == 3:
    for lab, c in zip(labels, picked):
        y0, y1, bb = c
        x0, x1 = int(W * 0.80) + bb[0], int(W * 0.80) + bb[2]
        crop = full.crop((x0, y0, x1, y1))
        bb2 = bbox_from(np.asarray(crop)[:, :, 3] > 12)
        if bb2:
            crop = crop.crop(bb2)
        crop = clean_alpha(crop)
        crop.save('assets/detail-%s.png' % lab)
        print('saved assets/detail-%s.png' % lab, crop.size, 'box', (x0, y0, x1, y1))
else:
    print('WARN: close-up boxes not detected as 3, got', len(picked))

# --- 预览图（棋盘底 + 三视图 + 特写） ---
pv = Image.new('RGBA', (W, H), (32, 40, 48, 255))
dr = ImageDraw.Draw(pv)
for yy in range(0, H, 32):
    for xx in range(0, W, 32):
        if (xx // 32 + yy // 32) % 2:
            dr.rectangle([xx, yy, xx + 31, yy + 31], fill=(46, 56, 66, 255))
for i, n in enumerate(names):
    try:
        s = Image.open('assets/breeze-%s.png' % n)
    except Exception as e:
        print('missing', n, e); continue
    sc = min(1.0, 820.0 / s.size[1])
    s2 = s.resize((int(s.size[0] * sc), int(s.size[1] * sc)), Image.LANCZOS)
    pv.alpha_composite(s2, (60 + i * 300, 60))
x = 980
for lab in ['face', 'paw', 'mouth']:
    try:
        s = Image.open('assets/detail-%s.png' % lab)
    except Exception:
        continue
    sc = min(1.0, 220.0 / max(s.size))
    s2 = s.resize((int(s.size[0] * sc), int(s.size[1] * sc)), Image.LANCZOS)
    pv.alpha_composite(s2, (x, 60))
    x += s2.size[0] + 20
pv.convert('RGB').resize((1152, 768), Image.LANCZOS).save('art-preview.png')
print('preview saved')

# -*- coding: utf-8 -*-
"""从创作者的三张走路循环图（正/侧/背 各 8 帧）抠出动画帧。
要点：
- 白底 + 灰色投影用“低彩度 + 高亮度”判据去掉（保护淡紫色尾巴与白色毛发）
- 连通块分割：每张图取面积最大的 8 个连通块 = 8 帧角色（自动排除编号圆牌与文字标签）
- 同一视图的 8 帧用【同一个】身体中轴锚点，避免逐帧重新居中造成的左右摇晃
"""
from PIL import Image, ImageFilter
import numpy as np

SRC = {'front': 'assets/walk-front.png', 'side': 'assets/walk-side.png', 'back': 'assets/walk-back.png'}
FLIP_SIDE = True     # 侧视统一成“朝左”，与设定图 breeze-side.png 一致


def dilate(m, r):
    out = m.copy()
    for _ in range(r):
        n = out.copy()
        n[1:, :] |= out[:-1, :]; n[:-1, :] |= out[1:, :]
        n[:, 1:] |= out[:, :-1]; n[:, :-1] |= out[:, 1:]
        out = n
    return out


def erode(m, r):
    out = m.copy()
    for _ in range(r):
        n = out.copy()
        n[1:, :] &= out[:-1, :]; n[:-1, :] &= out[1:, :]
        n[:, 1:] &= out[:, :-1]; n[:, :-1] &= out[:, 1:]
        out = n
    return out


def keyed(path):
    im = Image.open(path).convert('RGB')
    a = np.asarray(im).astype(np.int16)
    d = (255 - a).sum(axis=2)
    mx = a.max(axis=2); mn = a.min(axis=2)
    chroma = mx - mn
    lum = a.mean(axis=2)
    bg = d < 100                                   # 近白：背景与白毛同色（都是 254,254,254）
    grayish = (chroma < 14) & (lum > 130) & (lum < 242)   # 投影 / 网格线 / 墨线抗锯齿边
    # 网格线贯穿整幅，先按几何清掉，否则每格会被封闭起来
    colfrac = grayish.mean(axis=0); rowfrac = grayish.mean(axis=1)
    for c in np.where(colfrac > 0.7)[0]:
        bg[:, c] = True
    for r in np.where(rowfrac > 0.7)[0]:
        bg[r, :] = True
    # 关键：墨线只有 1~2px 且抗锯齿后接近白色，颜色上无法与背景区分 ——
    # 用闭运算把这些细缝先封死，泛洪就不会顺着缝漏进白毛里
    fg = erode(dilate(~bg, 3), 3)
    conn = np.zeros_like(bg)
    conn[0, :] |= (~fg)[0, :]; conn[-1, :] |= (~fg)[-1, :]
    conn[:, 0] |= (~fg)[:, 0]; conn[:, -1] |= (~fg)[:, -1]
    conn &= ~fg
    for _ in range(4000):
        nxt = conn.copy()
        nxt[1:, :] |= conn[:-1, :]; nxt[:-1, :] |= conn[1:, :]
        nxt[:, 1:] |= conn[:, :-1]; nxt[:, :-1] |= conn[:, 1:]
        nxt &= ~fg
        if nxt.sum() == conn.sum():
            break
        conn = nxt
    # 二次：向外吞并紧贴背景的中性灰（投影与墨线抗锯齿边）；角色本体被墨线隔开，碰不到
    for _ in range(80):
        nxt = conn.copy()
        nxt[1:, :] |= conn[:-1, :]; nxt[:-1, :] |= conn[1:, :]
        nxt[:, 1:] |= conn[:, :-1]; nxt[:, :-1] |= conn[:, 1:]
        nxt &= (conn | (grayish & ~fg) | bg)
        if nxt.sum() == conn.sum():
            break
        conn = nxt
    alpha = np.where(conn, 0, 255).astype(np.uint8)
    out = Image.fromarray(np.dstack([np.asarray(im), alpha]), 'RGBA')
    # 清掉下方（图片底部 35% 区域）的蓝色编号/文字标签行。
    # 判据必须排除薄荷青的爪垫：标签是宝蓝（绿通道低），爪垫是青色（绿通道高）
    strong_blue = (a[:, :, 2] - a[:, :, 0] > 90) & (a[:, :, 2] > 140) & (a[:, :, 1] < 170)
    y0 = int(alpha.shape[0] * 0.65)
    arr = np.asarray(out).copy()
    for yy in range(y0, alpha.shape[0]):
        if strong_blue[yy].sum() > 25:
            arr[yy, :, 3] = 0
    out = Image.fromarray(arr, 'RGBA')
    # 形态学开运算：去掉贴边的白描边/光晕等 1~2px 细结构，主体形状不变
    al = out.getchannel('A').filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    al = al.filter(ImageFilter.GaussianBlur(0.6))
    out.putalpha(al)
    # 去掉脚下残留的灰色小碎点（只擦这些连通块自身的像素，绝不能擦外接矩形）
    arr = np.asarray(out).copy()
    fgm = arr[:, :, 3] > 24
    for (cx0, cy0, cx1, cy1, carea) in components(fgm):
        if carea < 600:
            sub = fgm[cy0:cy1, cx0:cx1]
            arr[cy0:cy1, cx0:cx1, 3][sub] = 0
    out = Image.fromarray(arr, 'RGBA')
    return out


def components(mask):
    work = mask.copy()
    out = []
    while True:
        ys, xs = np.where(work)
        if len(xs) == 0:
            break
        cur = np.zeros_like(work)
        cur[ys[0], xs[0]] = True
        while True:
            nxt = cur.copy()
            nxt[1:, :] |= cur[:-1, :]; nxt[:-1, :] |= cur[1:, :]
            nxt[:, 1:] |= cur[:, :-1]; nxt[:, :-1] |= cur[:, 1:]
            nxt &= work
            if nxt.sum() == cur.sum():
                break
            cur = nxt
        yy, xx = np.where(cur)
        out.append((int(xx.min()), int(yy.min()), int(xx.max()) + 1, int(yy.max()) + 1, int(cur.sum())))
        work[cur] = False
    return out


for view, path in SRC.items():
    full = keyed(path)
    fg = np.asarray(full)[:, :, 3] > 20
    raw = [c for c in components(fg) if c[4] > 400]
    # 排除编号圆牌与蓝色文字标签：彩度极高的蓝（角色毛色蓝得没那么纯）
    keep = []
    for c in raw:
        patch = np.asarray(full)[c[1]:c[3], c[0]:c[2]]
        m = patch[:, :, 3] > 20
        if m.sum() == 0:
            continue
        mr = patch[:, :, 0][m].mean(); mb = patch[:, :, 2][m].mean()
        if (mb - mr) > 80 and c[4] < 6000:
            continue
        keep.append(c)
    raw = keep
    # 合并属于同一角色的碎块（开运算可能把头/身、尾巴切开）
    used = [False] * len(raw)
    merged = []
    for i in range(len(raw)):
        if used[i]:
            continue
        group = [raw[i]]; used[i] = True
        changed = True
        while changed:
            changed = False
            for j in range(len(raw)):
                if used[j]:
                    continue
                d = raw[j]
                for m in group:
                    ox = min(m[2], d[2]) - max(m[0], d[0])
                    if ox > 0.6 * min(m[2] - m[0], d[2] - d[0]) and d[1] < m[3] + 30 and d[3] > m[1] - 30:
                        group.append(d); used[j] = True; changed = True
                        break
        merged.append((min(g[0] for g in group), min(g[1] for g in group),
                       max(g[2] for g in group), max(g[3] for g in group),
                       sum(g[4] for g in group)))
    chars = [c for c in merged if c[4] > 6000]         # 只留角色，排除编号圆牌与文字
    rowH = max(1, int(np.median([c[3] - c[1] for c in chars])))
    chars.sort(key=lambda c: (round((c[1] + c[3]) / 2 / rowH / 1.02), c[0]))
    chars = chars[:8]
    print('%s: %d 帧, 尺寸 %s' % (view, len(chars), [(c[2] - c[0], c[3] - c[1]) for c in chars]))

    axs, bots = [], []
    for (bx0, by0, bx1, by1, _) in chars:
        m = fg[by0:by1, bx0:bx1]
        h = m.shape[0]
        mid = m[int(h * 0.4):int(h * 0.66), :]
        xs = np.where(mid.any(axis=0))[0]
        axs.append(bx0 + (xs.mean() if len(xs) else (bx1 - bx0) / 2))
        bots.append(by1)
    A = float(np.median(axs))                          # 8 帧共用的中轴
    B = float(np.median(bots))
    print('   锚点 x=%.1f 基线 y=%.1f' % (A, B))

    maxW = int(max(c[2] - c[0] for c in chars) + 30)
    maxH = int(max(c[3] - c[1] for c in chars) + 8)   # 每帧按自身脚底对齐（网格图有两行）
    for i, (bx0, by0, bx1, by1, _) in enumerate(chars):
        crop = full.crop((bx0, by0, bx1, by1))
        ax = axs[i]
        if view == 'side' and FLIP_SIDE:
            # 新走路的侧视朝右，而设定图侧视朝左 —— 统一镜像成朝左
            crop = crop.transpose(Image.FLIP_LEFT_RIGHT)
            ax = (bx0 + bx1) - ax
        canvas = Image.new('RGBA', (maxW, maxH), (0, 0, 0, 0))
        px = int(round(maxW / 2 - (ax - bx0)))         # 按该帧自身躯干中轴居中
        py = maxH - (by1 - by0)
        canvas.alpha_composite(crop, (max(0, px), max(0, py)))
        # 只保留与本体同量级的大块：清掉脱落的爪垫碎块（否则看起来像多了一只脚）
        ca = np.asarray(canvas)
        msk = ca[:, :, 3] > 24
        cs = components(msk)
        if cs:
            big = max(c[4] for c in cs)
            arr2 = ca.copy()
            for (a0, b0, a1, b1, ar) in cs:
                if ar < big * 0.06:
                    sub = msk[b0:b1, a0:a1]
                    arr2[b0:b1, a0:a1, 3][sub] = 0
            canvas = Image.fromarray(arr2, 'RGBA')
        canvas.save('assets/walk-%s-%d.png' % (view, i))
    print('   保存 %d 帧，画布 %dx%d' % (len(chars), maxW, maxH))

pv = Image.new('RGBA', (1560, 620), (26, 32, 40, 255))
y = 6
for view in ['front', 'side', 'back']:
    x = 6
    for i in range(8):
        f = Image.open('assets/walk-%s-%d.png' % (view, i))
        sc = 196.0 / f.size[1]
        f2 = f.resize((max(1, int(f.size[0] * sc)), int(f.size[1] * sc)), Image.LANCZOS)
        pv.alpha_composite(f2, (x, y))
        x += f2.size[0] + 2
    y += 200
pv.convert('RGB').save('walk-preview.png')
print('preview saved')

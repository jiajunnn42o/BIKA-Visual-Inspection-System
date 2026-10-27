"""
prawn_occlusion.py  虾条遮挡过滤 (网站用，只依赖 numpy + cv2)

和 D:\\SAM3prawn\\scripts\\02_classify_instances.py 同一套规则，用来决定哪些 mask 要判断质量：
  usable (判断)  : isolated / side_contact / end_long
  不判断          : partial (形状不完整) / multi_part / oversize / border / thin / end_contact (端部被压)

输入 preds 的格式和 09b 一样: {"box": (x0,y0,x1,y1) 含端点, "local": bool mask, "area", "conf", "cx", "cy"}
用法:
    statuses = classify_statuses(preds, H, W, cfg)      # cfg = 03_occlusion_filter.json 的内容
    judge = [s in USABLE for s in statuses]
"""
from __future__ import annotations

import heapq

import cv2
import numpy as np

USABLE = ("isolated", "side_contact", "end_long")

DEFAULTS = {
    "contact_dilate": 3,
    "end_perp_k": 0.35,
    "tan_r": 10,
    "end_min_px": 4,
    "thin_k": 0.65,
    "wide_k": 1.8,
    "narrow_k": 0.45,
    "min_aspect": 1.3,
    "width_cv_max": 0.40,
    "min_area_k": 0.08,
    "oversize_k": 2.2,
    "edge_tol": 3,
    "end_long_k": 0.9,
}


# ============================================================
# 骨架
# ============================================================

# scikit-image 0.26 skeletonize (Zhang-Suen 变体) 的查找表，逐字照抄，结果和 02 (skimage) 完全一致
_SK_LUT = np.array([
    0, 0, 0, 1, 0, 0, 1, 3, 0, 0, 3, 1, 1, 0, 1, 3, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 2, 0,
    3, 0, 3, 3, 0, 0, 0, 0, 0, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    2, 0, 0, 0, 3, 0, 2, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 2, 0, 0, 0,
    3, 0, 0, 0, 0, 0, 0, 0, 3, 0, 0, 0, 3, 0, 2, 0, 0, 0, 3, 1, 0, 0, 1, 3, 0, 0, 0, 0,
    0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 3, 1, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 3, 1, 3,
    0, 0, 1, 3, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    2, 3, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 3, 3, 0, 1, 0, 0, 0, 0, 2, 2, 0, 0,
    2, 0, 0, 0], dtype=np.uint8)


def zhang_suen(mask):
    """和 skimage.morphology.skeletonize (2D) 相同的结果，numpy 向量化"""
    sk = np.pad(mask.astype(np.uint8), 1)
    while True:
        removed = False
        for first in (True, False):
            P = sk
            code = (P[:-2, :-2] + 2 * P[:-2, 1:-1] + 4 * P[:-2, 2:] + 8 * P[1:-1, 2:]
                    + 16 * P[2:, 2:] + 32 * P[2:, 1:-1] + 64 * P[2:, :-2] + 128 * P[1:-1, :-2])
            t = _SK_LUT[code]
            rem = (P[1:-1, 1:-1] == 1) & ((t == 3) | ((t == 1) if first else (t == 2)))
            if rem.any():
                sk = sk.copy()
                sk[1:-1, 1:-1][rem] = 0
                removed = True
        if not removed:
            break
    return sk[1:-1, 1:-1].astype(bool)


def longest_path(sk):
    """骨架像素 8 邻接图上的最长路径 (两次 Dijkstra)。返回 (N,2) 的 (y,x) 或 None"""
    ys, xs = np.nonzero(sk)
    n = len(ys)
    if n < 2:
        return None
    idx = {(int(y), int(x)): i for i, (y, x) in enumerate(zip(ys, xs))}
    nbrs = [[] for _ in range(n)]
    for i, (y, x) in enumerate(zip(ys, xs)):
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                j = idx.get((int(y) + dy, int(x) + dx))
                if j is not None:
                    nbrs[i].append((j, 1.4142135623730951 if dy and dx else 1.0))

    def dijkstra(src):
        dist = [float("inf")] * n
        pred = [-1] * n
        dist[src] = 0.0
        h = [(0.0, src)]
        while h:
            d, u = heapq.heappop(h)
            if d > dist[u]:
                continue
            for v, w in nbrs[u]:
                nd = d + w
                if nd < dist[v]:
                    dist[v], pred[v] = nd, u
                    heapq.heappush(h, (nd, v))
        return dist, pred

    d0, _ = dijkstra(0)
    a = max((i for i in range(n) if d0[i] < float("inf")), key=lambda i: d0[i])
    da, pred = dijkstra(a)
    b = max((i for i in range(n) if da[i] < float("inf")), key=lambda i: da[i])
    seq = [b]
    while seq[-1] != a and pred[seq[-1]] >= 0:
        seq.append(pred[seq[-1]])
    seq = seq[::-1]
    return np.stack([ys[seq], xs[seq]], 1)


# ============================================================
# 单个 mask 的几何 (和 02.geom 一致)
# ============================================================

def geom(m, tan_r):
    area = int(m.sum())
    mu = m.astype(np.uint8)
    cs, _ = cv2.findContours(mu, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cs, key=cv2.contourArea)
    solidity = area / max(cv2.contourArea(cv2.convexHull(c)), 1.0)
    (_, _), (rw, rh), _ = cv2.minAreaRect(c)
    _, _, stats, _ = cv2.connectedComponentsWithStats(mu, connectivity=8)
    parts = int((stats[1:, cv2.CC_STAT_AREA] >= 0.05 * area).sum())
    rect_aspect = max(rw, rh) / max(min(rw, rh), 1.0)

    mp = np.pad(mu, 1)
    sk = zhang_suen(mp)
    dt = cv2.distanceTransform(mp, cv2.DIST_L2, 5)
    width_cv, ends = 0.0, []
    path = longest_path(sk)
    if path is not None and len(path) >= 2:
        py, px = path[:, 0], path[:, 1]
        path_len = float(np.hypot(np.diff(py), np.diff(px)).sum())
        r_a, r_b = float(dt[py[0], px[0]]), float(dt[py[-1], px[-1]])
        length = path_len + r_a + r_b
        pts = np.stack([px, py], 1).astype(np.float64) - 1.0
        e1, e2 = pts[0], pts[-1]
        dist = float(np.hypot(*(e1 - e2)))
        dpath = dt[py, px]
        w_est = 2.0 * float(np.median(dpath))
        dmin = np.minimum(np.hypot(*(pts - e1).T), np.hypot(*(pts - e2).T))
        cen = dpath[dmin > w_est] if (dmin > w_est).sum() >= 3 else dpath
        width = 2.0 * float(np.median(cen))
        if len(cen) >= 3:
            width_cv = float((np.percentile(cen, 90) - np.percentile(cen, 10)) / max(np.percentile(cen, 50), 1e-6))
        for e, sl in ((e1, slice(0, tan_r)), (e2, slice(-tan_r, None))):
            v = e - pts[sl].mean(0)
            nrm = np.hypot(*v)
            if nrm < 1e-3:
                v = e - pts.mean(0)
                nrm = max(np.hypot(*v), 1e-3)
            ends.append((e, v / nrm))
        straight = min(dist / max(path_len, 1.0), 1.0)
    else:
        length = float(max(rw, rh))
        width = float(max(min(rw, rh), 1.0))
        straight = float("nan")
    return dict(area=area, solidity=solidity, parts=parts, width=width, length=length,
                aspect=length / max(width, 1e-6), straight=straight, ends=ends,
                rect_aspect=rect_aspect, width_cv=width_cv)


def length_mode(L, bin_w=4.0):
    L = np.asarray(L, float)
    if len(L) < 5:
        return float(np.median(L)) if len(L) else 1.0
    bins = np.arange(L.min(), L.max() + bin_w, bin_w)
    if len(bins) < 3:
        return float(np.median(L))
    h, e = np.histogram(L, bins)
    h = np.convolve(h, np.array([1, 2, 3, 2, 1], float), mode="same")
    i = int(np.argmax(h))
    return float((e[i] + e[i + 1]) / 2)


# ============================================================
# 整张图
# ============================================================

def classify_statuses(preds, H, W, cfg=None, return_features=False):
    """返回每个 pred 的状态 (和 02 相同的名字)"""
    c = dict(DEFAULTS, **(cfg or {}))
    if not preds:
        return ([], []) if return_features else []

    G = []
    for p in preds:
        m = np.asarray(p["local"], bool)
        x0, y0 = int(p["box"][0]), int(p["box"][1])
        g = geom(m, int(c["tan_r"]))
        g.update(m=m, x0=x0, y0=y0)
        G.append(g)

    good = [g for g in G if g["aspect"] >= 2.5 and g["solidity"] >= 0.8 and g["parts"] == 1]
    ref = good if len(good) >= 10 else G
    medW = float(np.median([g["width"] for g in ref]))
    medA = float(np.median([g["area"] for g in ref]))

    for g in G:
        why = []
        if g["aspect"] < c["min_aspect"] or g["rect_aspect"] < c["min_aspect"]:
            why.append("aspect")
        if g["width_cv"] > c["width_cv_max"]:
            why.append("width_cv")
        if g["width"] > c["wide_k"] * medW:
            why.append("wide")
        if g["width"] < c["narrow_k"] * medW:
            why.append("narrow")
        if g["area"] < c["min_area_k"] * medA:
            why.append("small")
        g["why"], g["partial"] = why, bool(why)
        g["junk"] = ("aspect" in why) or ("small" in why)

    cd = int(c["contact_dilate"])
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * cd + 1,) * 2)
    cnt = np.zeros((H, W), np.int32)
    for g in G:
        dil = cv2.dilate(np.pad(g["m"].astype(np.uint8), cd), k)
        h, w = dil.shape
        gx0, gy0 = g["x0"] - cd, g["y0"] - cd
        cx0, cy0, cx1, cy1 = max(gx0, 0), max(gy0, 0), min(gx0 + w, W), min(gy0 + h, H)
        g["reg"] = (cy0, cy1, cx0, cx1)
        g["dil"] = dil[cy0 - gy0:cy1 - gy0, cx0 - gx0:cx1 - gx0]
        if not g["junk"]:
            cnt[cy0:cy1, cx0:cx1] += g["dil"]

    tol = int(c["edge_tol"])
    for g in G:
        h, w = g["m"].shape
        x0, y0 = g["x0"], g["y0"]
        cy0, cy1, cx0, cx1 = g["reg"]
        own = g["dil"] if not g["junk"] else 0
        others = cnt[cy0:cy1, cx0:cx1] - own
        yy, xx = np.nonzero((others > 0) & (g["dil"] > 0))
        n_contact, n_cap = len(xx), 0
        if n_contact and g["ends"]:
            Pl = np.stack([xx + cx0 - x0, yy + cy0 - y0], 1).astype(np.float64)
            for e, v in g["ends"]:
                q = Pl - e
                along = q @ v
                perp = np.abs(q[:, 0] * v[1] - q[:, 1] * v[0])
                n_cap += int(((along > 0) & (perp < c["end_perp_k"] * medW)).sum())
        border = x0 <= tol or y0 <= tol or x0 + w >= W - 1 - tol or y0 + h >= H - 1 - tol
        if g["partial"]:
            st = "partial"
        elif g["parts"] > 1:
            st = "multi_part"
        elif g["area"] > c["oversize_k"] * medA:
            st = "oversize"
        elif border:
            st = "border"
        elif g["width"] < c["thin_k"] * medW:
            st = "thin"
        elif n_cap >= c["end_min_px"]:
            st = "end_contact"
        elif n_contact:
            st = "side_contact"
        else:
            st = "isolated"
        g["status"] = st

    ref_l = [g["length"] for g in G if g["status"] in ("isolated", "side_contact", "end_contact")]
    if len(ref_l) < 20:
        ref_l = [g["length"] for g in good] or [g["length"] for g in G]
    ref_len = length_mode(ref_l)
    for g in G:
        if g["status"] == "end_contact" and g["length"] >= c["end_long_k"] * ref_len:
            g["status"] = "end_long"

    statuses = [g["status"] for g in G]
    if return_features:
        feats = [{"length": g["length"], "width": g["width"], "width_cv": g["width_cv"],
                  "aspect": g["aspect"], "why": "+".join(g["why"])} for g in G]
        return statuses, feats
    return statuses


# ============================================================
# 哪些 mask 要判断
# ============================================================
# mode "all"     : 全部都判断 (不分碎块)
# mode "strict"  : 只判断 USABLE (isolated / side_contact / end_long)
# mode "lenient" : 除了碎块都判断。碎块 = 整个 mask (所有像素) 的最小外接矩形长宽比 < frag_aspect
#                  (只露出圆圆一颗)，或面积很小 ("small")。oversize (两根粘成一个) 和 border (被图片边切断) 也不判断。
#                  用所有像素的外接矩形：被上面一根压成两段的虾条，两段连起来还是长条 -> 会判断
NOT_JUDGED_LENIENT = ("oversize", "border")


def rect_aspect_all(local):
    ys, xs = np.nonzero(np.asarray(local, bool))
    if len(xs) < 3:
        return 1.0
    (_, _), (rw, rh), _ = cv2.minAreaRect(np.stack([xs, ys], 1).astype(np.float32))
    return float(max(rw, rh) / max(min(rw, rh), 1.0))


def judge_reason(status, rect_aspect, why, cfg=None):
    """"" = 要判断；否则返回不判断的原因 (网站上显示)"""
    c = dict(DEFAULTS, **(cfg or {}))
    mode = c.get("mode", "strict")
    if mode == "all":                      # 关掉灰色：SAM3 找到的全部都判断
        return ""
    if mode != "lenient":
        return "" if status in USABLE else status
    if status == "border":
        return "cut by image edge"
    if status == "oversize":
        return "merged mask (oversize)"
    if "small" in str(why):
        return "too small"
    if float(rect_aspect) < float(c.get("frag_aspect", 2.0)):
        return f"round fragment (aspect {float(rect_aspect):.1f})"
    return ""


def is_judged(status, rect_aspect, why, cfg=None):
    return judge_reason(status, rect_aspect, why, cfg) == ""


def scaled_preds(preds, s, W_small=None, H_small=None):
    """preds (原图坐标) -> 缩小 s 倍后的 preds (同样的顺序)，W_small/H_small = 缩小后图的大小 (用来裁边)"""
    out = []
    for p in preds:
        x0, y0 = p["box"][0], p["box"][1]
        h, w = p["local"].shape
        nw, nh = max(1, int(round(w * s))), max(1, int(round(h * s)))
        loc = cv2.resize(p["local"].astype(np.uint8) * 255, (nw, nh), interpolation=cv2.INTER_AREA) > 127
        if not loc.any():
            loc = np.zeros((nh, nw), bool)
            loc[nh // 2, nw // 2] = True
        X0, Y0 = int(round(x0 * s)), int(round(y0 * s))
        if W_small is not None:
            X0 = min(X0, W_small - 1)
            loc = loc[:, :max(1, W_small - X0)]
        if H_small is not None:
            Y0 = min(Y0, H_small - 1)
            loc = loc[:max(1, H_small - Y0), :]
        ys, xs = np.nonzero(loc)
        if len(xs) == 0:
            loc[0, 0] = True
            ys, xs = np.array([0]), np.array([0])
        out.append({"box": (X0, Y0, X0 + loc.shape[1] - 1, Y0 + loc.shape[0] - 1), "local": loc,
                    "area": int(loc.sum()), "conf": p.get("conf", 1.0),
                    "cx": float(X0 + xs.mean()), "cy": float(Y0 + ys.mean())})
    return out


def judge_details(preds, H, W, cfg=None, scale=1.0):
    """-> (judged: list[bool], statuses: list[str], reasons: list[str])
    scale < 1: 在 SAM3 缩小后的尺度上算 (和离线 02 的视频帧尺度一致，也快很多)"""
    if scale and scale < 0.999:
        H, W = max(1, int(round(H * scale))), max(1, int(round(W * scale)))
        preds = scaled_preds(preds, scale, W, H)
    st, ft = classify_statuses(preds, H, W, cfg, return_features=True)
    reasons = [judge_reason(s, rect_aspect_all(p["local"]), f["why"], cfg) for p, s, f in zip(preds, st, ft)]
    return [r == "" for r in reasons], st, reasons


def judge_flags(preds, H, W, cfg=None, scale=1.0):
    """-> (judged: list[bool], statuses: list[str])"""
    judged, st, _ = judge_details(preds, H, W, cfg, scale)
    return judged, st
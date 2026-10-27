"""
sam3_segmenter.py  v3 (虾条) 用 SAM3.1 直接出 mask，代替 YOLO + SAM2
和 D:\\SAM3prawn\\scripts\\01_sam3_probe.py 完全相同的做法：
  4x3 切块 -> 每块 text prompt "stick" -> 自动挑 3 根当示例框 -> 第二遍推理 -> 去掉被块边切断的 -> 全图 NMS
输出 preds 和 09b.segment() 同格式：{"box": (x0,y0,x1,y1) 含端点, "local", "area", "conf", "cx", "cy"}

segmenter.json (放在模型文件夹，和 classifier.pt 一起)：
  {"type": "sam3", "checkpoint": "../sam3/sam3.1_multiplex.pt", "prompt": "stick", ...}
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import torch

DEFAULTS = {
    "prompt": "stick",
    "tile_cols": 4, "tile_rows": 3, "tile_overlap": 200, "edge_tol": 3,
    "use_exemplar": True, "n_exemplar": 3, "ex_top_k": 30, "ex_min_aspect": 3.0,
    "conf_th": 0.30, "conf_th_text_only": 0.10,
    "nms_iou": 0.5, "nms_contain": 0.8, "min_pixels": 30,
    # 自动缩小：先用中间一块量虾条长度 L (75%)。如果 L x fit_k > tile_overlap
    # (高分辨率照片，虾条比 overlap 长 -> 跨块的两边都被切断 -> 漏检)，
    # 就把整张图缩小到 L x fit_k = tile_overlap 再切块，mask 最后放大回原图。
    # 切块布局 / overlap 不变 (和离线 01 一样)，不会因为块变大出现整堆一个大 mask。
    "auto_scale": True, "fit_k": 1.3, "min_scale_change": 0.7,
    "blob_area_k": 4.0,     # 比中位面积大 4 倍的 mask (整堆粘成一个) 不要
}


def build_processor(checkpoint, device="cuda"):
    from sam3.model_builder import build_sam3_image_model
    from sam3.model.sam3_image_processor import Sam3Processor
    model = build_sam3_image_model(device=device, checkpoint_path=str(checkpoint), load_from_HF=False)
    try:
        return Sam3Processor(model, confidence_threshold=0.0)
    except TypeError:
        return Sam3Processor(model)


def _to_np(out, tw, th, min_score=0.0, top_k=0):
    """只把 (分数 >= min_score 或 排名前 top_k) 的 mask 拿到 CPU，并且在 GPU 上先变成 bool，
    否则 200 个 float mask 要 2 GB+ 内存。
    注意：第一遍只有 text prompt 时分数只有 ~0.03，所以一定要留前 top_k 个给 _pick_exemplars"""
    masks, scores, boxes = out.get("masks"), out.get("scores"), out.get("boxes")
    if masks is None or len(masks) == 0:
        return np.zeros((0, th, tw), bool), np.zeros(0), np.zeros((0, 4))
    sc_t = scores.detach().float().reshape(-1)
    keep = sc_t >= min_score
    if top_k:
        keep[torch.argsort(sc_t, descending=True)[:top_k]] = True
    idx = keep.nonzero().reshape(-1)
    if idx.numel() == 0:
        return np.zeros((0, th, tw), bool), np.zeros(0), np.zeros((0, 4))
    m_t = masks.detach()[idx]
    m_t = (m_t > 0.5) if m_t.dtype != torch.bool else m_t
    m = m_t.cpu().numpy()
    m = m.reshape(m.shape[0], m.shape[-2], m.shape[-1])
    sc = sc_t[idx].cpu().numpy()
    b = boxes.detach().float().reshape(-1, 4)[idx].cpu().numpy()
    if len(b) and b.max() <= 1.5:
        b = b * np.array([tw, th, tw, th])
    return m, sc, b


def _pick_exemplars(m, sc, b, tw, th, c):
    tol = c["edge_tol"]
    cand = []
    for i in np.argsort(sc)[::-1][:c["ex_top_k"]]:
        x0, y0, x1, y1 = b[i]
        if x0 <= tol or y0 <= tol or x1 >= tw - 1 - tol or y1 >= th - 1 - tol:
            continue
        mu = m[i].astype(np.uint8)
        n, _, _, _ = cv2.connectedComponentsWithStats(mu, connectivity=8)
        if n - 1 != 1:
            continue
        cs, _ = cv2.findContours(mu, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        (_, _), (rw, rh), _ = cv2.minAreaRect(max(cs, key=cv2.contourArea))
        if max(rw, rh) / max(min(rw, rh), 1.0) < c["ex_min_aspect"]:
            continue
        cand.append((i, int(mu.sum())))
    if not cand:
        return []
    med = float(np.median([a for _, a in cand]))
    chosen, boxes = [], []
    for i, a in cand:
        if not (0.6 * med <= a <= 1.6 * med):
            continue
        if any(np.logical_and(m[i], m[j]).any() for j in chosen):
            continue
        chosen.append(i)
        x0, y0, x1, y1 = b[i]
        boxes.append([(x0 + x1) / 2 / tw, (y0 + y1) / 2 / th, (x1 - x0) / tw, (y1 - y0) / th])
        if len(chosen) >= c["n_exemplar"]:
            break
    return boxes


def _add_boxes(proc, st, boxes):
    """所有示例框一次加进去，只跑一次 grounding (结果和一个一个 add_geometric_prompt 一样，
    因为中间结果本来就丢掉)。旧版 sam3 不支持时退回一个一个加。"""
    try:
        if "language_features" not in st["backbone_out"] or "geometric_prompt" not in st:
            raise KeyError
        dev = getattr(proc, "device", "cuda")
        b = torch.tensor(boxes, device=dev, dtype=torch.float32).view(len(boxes), 1, 4)
        lab = torch.ones((len(boxes), 1), device=dev, dtype=torch.bool)
        st["geometric_prompt"].append_boxes(b, lab)
        return proc._forward_grounding(st)
    except Exception:
        for box in boxes:
            st = proc.add_geometric_prompt(box=box, label=True, state=st)
        return st


def _run_tile(proc, tile_rgb, c):
    """返回的 mask 可能比 tile 小 (大块先缩到 max_tile_side)，调用的地方会放大回 tile 大小"""
    from PIL import Image
    th, tw = tile_rgb.shape[:2]
    ms = int(c.get("max_tile_side", 1008))
    if max(th, tw) > ms:
        # SAM3 内部本来就把图缩到 1008 再算，所以先缩不影响结果；
        # 但 200 个 mask 会按输入大小放大成 float -> 大块时 GPU 显存暴涨 (OOM)
        f = ms / max(th, tw)
        tile_rgb = cv2.resize(tile_rgb, (max(1, round(tw * f)), max(1, round(th * f))), interpolation=cv2.INTER_AREA)
        th, tw = tile_rgb.shape[:2]
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16, enabled=torch.cuda.is_available()):
        st = proc.set_image(Image.fromarray(tile_rgb))
        st = proc.set_text_prompt(state=st, prompt=c["prompt"])
        m, sc, b = _to_np(st, tw, th, min_score=c["conf_th_text_only"],
                          top_k=c["ex_top_k"] if c["use_exemplar"] else 0)
        ex = _pick_exemplars(m, sc, b, tw, th, c) if c["use_exemplar"] and len(sc) else []
        if ex:
            st = _add_boxes(proc, st, ex)
            m, sc, b = _to_np(st, tw, th, min_score=c["conf_th"])
    keep = sc >= (c["conf_th"] if ex else c["conf_th_text_only"])
    return m[keep], sc[keep]


def _tiles(W, H, c):
    nc, nr, ov = c["tile_cols"], c["tile_rows"], c["tile_overlap"]
    tw = min(int(np.ceil((W + (nc - 1) * ov) / nc)), W)
    th = min(int(np.ceil((H + (nr - 1) * ov) / nr)), H)
    xs = [max(0, min(i * (tw - ov), W - tw)) for i in range(nc)]
    ys = [max(0, min(j * (th - ov), H - th)) for j in range(nr)]
    return [(x, y, x + tw, y + th) for y in ys for x in xs]


def _overlap(a, b):
    ax0, ay0, ax1, ay1 = a["box"]
    bx0, by0, bx1, by1 = b["box"]
    x0, y0, x1, y1 = max(ax0, bx0), max(ay0, by0), min(ax1, bx1), min(ay1, by1)
    if x1 < x0 or y1 < y0:
        return 0.0, 0.0
    sa = a["local"][y0 - ay0:y1 - ay0 + 1, x0 - ax0:x1 - ax0 + 1]
    sb = b["local"][y0 - by0:y1 - by0 + 1, x0 - bx0:x1 - bx0 + 1]
    inter = int(np.logical_and(sa, sb).sum())
    if inter == 0:
        return 0.0, 0.0
    return inter / (a["area"] + b["area"] - inter), inter / min(a["area"], b["area"])


def _long_side(mask):
    cs, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    (_, _), (rw, rh), _ = cv2.minAreaRect(max(cs, key=cv2.contourArea))
    return max(rw, rh), max(min(rw, rh), 1.0)


def estimate_length(proc, image_np, c):
    """中间一块 (和正常切块一样大) 里完整、细长的 mask -> 75% 长度 (px)，量不到返回 None"""
    H, W = image_np.shape[:2]
    x0, y0, x1, y1 = _tiles(W, H, c)[0]
    tw, th = x1 - x0, y1 - y0
    cx0, cy0 = (W - tw) // 2, (H - th) // 2
    tile = np.ascontiguousarray(image_np[cy0:cy0 + th, cx0:cx0 + tw])
    masks, _ = _run_tile(proc, tile, c)
    tol = c["edge_tol"]
    lens = []
    for m in masks:
        if m.shape != (th, tw):
            m = cv2.resize(m.astype(np.uint8) * 255, (tw, th), interpolation=cv2.INTER_LINEAR) > 127
        ys, xs = np.nonzero(m)
        if len(xs) < c["min_pixels"]:
            continue
        if xs.min() <= tol or ys.min() <= tol or xs.max() >= tw - 1 - tol or ys.max() >= th - 1 - tol:
            continue
        if cv2.connectedComponents(m.astype(np.uint8))[0] - 1 != 1:
            continue
        L, w = _long_side(m)
        if L / w >= 3.0:
            lens.append(L)
    if len(lens) < 5:
        return None
    return float(np.percentile(lens, 75))


def _segment_tiles(proc, image_np, c, cancel_check):
    H, W = image_np.shape[:2]
    tol = c["edge_tol"]
    cands = []
    for (x0, y0, x1, y1) in _tiles(W, H, c):
        if cancel_check is not None and cancel_check():
            break
        tile = np.ascontiguousarray(image_np[y0:y1, x0:x1])
        th, tw = tile.shape[:2]
        masks, scores = _run_tile(proc, tile, c)
        for m, sc in zip(masks, scores):
            if m.shape != (th, tw):
                m = cv2.resize(m.astype(np.uint8) * 255, (tw, th), interpolation=cv2.INTER_LINEAR) > 127
            ys, xs = np.nonzero(m)
            if len(xs) < c["min_pixels"]:
                continue
            mx0, mx1, my0, my1 = xs.min(), xs.max(), ys.min(), ys.max()
            if (mx0 <= tol and x0 > 0) or (mx1 >= tw - 1 - tol and x1 < W) or \
               (my0 <= tol and y0 > 0) or (my1 >= th - 1 - tol and y1 < H):
                continue                                    # 被块边切断，交给相邻的块
            local = m[my0:my1 + 1, mx0:mx1 + 1].copy()
            cands.append(_pred(local, int(x0 + mx0), int(y0 + my0), float(sc)))
    if len(cands) >= 10 and c.get("blob_area_k"):
        med = float(np.median([p["area"] for p in cands]))
        cands = [p for p in cands if p["area"] <= c["blob_area_k"] * med]
    kept = []
    for p in sorted(cands, key=lambda q: -q["conf"]):
        dup = False
        for k in kept:
            iou, cont = _overlap(p, k)
            if iou > c["nms_iou"] or cont > c["nms_contain"]:
                dup = True
                break
        if not dup:
            kept.append(p)
    return kept


def _pred(local, gx0, gy0, conf):
    ly, lx = np.nonzero(local)
    return {"box": (gx0, gy0, gx0 + local.shape[1] - 1, gy0 + local.shape[0] - 1),
            "local": local, "area": int(local.sum()), "conf": conf,
            "cx": float(lx.mean() + gx0), "cy": float(ly.mean() + gy0)}


def _upscale(p, s, W, H):
    """小图上的 pred -> 原图坐标 (mask 线性插值放大再 > 0.5)"""
    x0, y0, x1, y1 = p["box"]
    X0, Y0 = int(np.floor(x0 / s)), int(np.floor(y0 / s))
    X1, Y1 = min(int(np.ceil((x1 + 1) / s)) - 1, W - 1), min(int(np.ceil((y1 + 1) / s)) - 1, H - 1)
    big = cv2.resize(p["local"].astype(np.float32), (X1 - X0 + 1, Y1 - Y0 + 1),
                     interpolation=cv2.INTER_LINEAR) > 0.5
    ys, xs = np.nonzero(big)
    if len(xs) == 0:
        return None
    local = big[ys.min():ys.max() + 1, xs.min():xs.max() + 1].copy()
    return _pred(local, X0 + int(xs.min()), Y0 + int(ys.min()), p["conf"])


def segment(proc, image_np, cfg=None, cancel_check=None, info=None):
    """整张图 -> preds (按置信度从高到低，原图坐标)。info (dict) 会填 scale / 虾条长度，方便 log"""
    c = dict(DEFAULTS, **(cfg or {}))
    H, W = image_np.shape[:2]
    s, L = 1.0, None
    if c.get("auto_scale", True):
        L = estimate_length(proc, image_np, c)
        if L is not None:
            want = c["tile_overlap"] / (c["fit_k"] * L)
            if want < c["min_scale_change"]:
                s = float(want)
    if info is not None:
        info.update({"scale": round(s, 3), "stick_len_p75": None if L is None else round(L, 1),
                     "overlap": c["tile_overlap"]})
    try:
        if s >= 1.0:
            return _segment_tiles(proc, image_np, c, cancel_check)
        return _segment_small(proc, image_np, c, cancel_check, s, W, H)
    finally:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()      # 把暂存的显存还给系统 (其它程序 / 下一张图)


def _segment_small(proc, image_np, c, cancel_check, s, W, H):
    small = cv2.resize(image_np, (max(1, round(W * s)), max(1, round(H * s))), interpolation=cv2.INTER_AREA)
    sx, sy = small.shape[1] / W, small.shape[0] / H
    out = []
    for p in _segment_tiles(proc, small, c, cancel_check):
        q = _upscale(p, (sx + sy) / 2, W, H)
        if q is not None and q["area"] >= c["min_pixels"]:
            out.append(q)
    return out
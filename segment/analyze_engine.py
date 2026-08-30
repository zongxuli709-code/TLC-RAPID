# Ultralytics YOLOv5 🚀, AGPL-3.0 license
"""
Run YOLOv5 segmentation inference on images, videos, directories, streams, etc.

Usage - sources:
    $ python segment/predict.py --weights yolov5s-seg.pt --source 0                               # webcam
                                                                  img.jpg                         # image
                                                                  vid.mp4                         # video
                                                                  screen                          # screenshot
                                                                  path/                           # directory
                                                                  list.txt                        # list of images
                                                                  list.streams                    # list of streams
                                                                  'path/*.jpg'                    # glob
                                                                  'https://youtu.be/LNwODJXcvt4'  # YouTube
                                                                  'rtsp://example.com/media.mp4'  # RTSP, RTMP, HTTP stream

Usage - formats:
    $ python segment/predict.py --weights yolov5s-seg.pt                 # PyTorch
                                          yolov5s-seg.torchscript        # TorchScript
                                          yolov5s-seg.onnx               # ONNX Runtime or OpenCV DNN with --dnn
                                          yolov5s-seg_openvino_model     # OpenVINO
                                          yolov5s-seg.engine             # TensorRT
                                          yolov5s-seg.mlmodel            # CoreML (macOS-only)
                                          yolov5s-seg_saved_model        # TensorFlow SavedModel
                                          yolov5s-seg.pb                 # TensorFlow GraphDef
                                          yolov5s-seg.tflite             # TensorFlow Lite
                                          yolov5s-seg_edgetpu.tflite     # TensorFlow Edge TPU
                                          yolov5s-seg_paddle_model       # PaddlePaddle
"""

import argparse
import json
import os
import platform
import sys
from datetime import datetime
from pathlib import Path
import pandas as pd
import numpy as np
from scipy import integrate
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import r2_score
from scipy import stats

import torch

FILE = Path(__file__).resolve()
if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = FILE.parents[1]
    if str(ROOT) not in sys.path:
        sys.path.append(str(ROOT))

from ultralytics.utils.plotting import Annotator, colors, save_one_box

from models.common import DetectMultiBackend
from utils.dataloaders import IMG_FORMATS, VID_FORMATS, LoadImages, LoadScreenshots, LoadStreams
from utils.general import (
    LOGGER,
    Profile,
    check_file,
    check_img_size,
    check_imshow,
    check_requirements,
    colorstr,
    cv2,
    increment_path,
    non_max_suppression,
    print_args,
    scale_boxes,
    scale_segments,
    strip_optimizer,
    yaml_save,
)
from utils.augmentations import letterbox
from utils.segment.general import masks2segments, process_mask, process_mask_native
from utils.torch_utils import select_device, smart_inference_mode


def choose_reference_y_from_boxes_xyxy(boxes: np.ndarray, y_tolerance: int = 60) -> int | None:
    """
    改进版：优先使用"最左侧点"的 y 坐标作为参考，确保左边点不被遮盖。
    如果第一次检测时左边点没有被检测到，则使用所有检测点的 y 坐标中位数。
    
    这样即使左边有些斑点稍微偏离，也能被包含在水平带内。
    """
    if boxes is None or len(boxes) == 0:
        return None
    boxes = np.asarray(boxes)
    x_centers = ((boxes[:, 0] + boxes[:, 2]) / 2.0).astype(float)
    y_centers = ((boxes[:, 1] + boxes[:, 3]) / 2.0).astype(float)
    
    if len(boxes) >= 1:
        # 优先使用最左侧点的 y 坐标（确保左边点不被遮盖）
        idx_leftmost = int(np.argmin(x_centers))
        y_ref_leftmost = float(y_centers[idx_leftmost])
        
        # 如果点数足够多，检查是否有其他点与最左侧点在同一水平带内
        if len(boxes) >= 2:
            in_band = np.abs(y_centers - y_ref_leftmost) <= float(y_tolerance)
            in_band_indices = np.where(in_band)[0]
            
            if len(in_band_indices) >= 2:
                # 使用同一水平带内所有点的 y 坐标中位数（更稳定）
                y_ref_median = float(np.median(y_centers[in_band_indices]))
                return int(round(y_ref_median))
        
        # 如果点数太少或没有足够的点在同一水平带，使用最左侧点
        return int(round(y_ref_leftmost))
    else:
        # 只有一个点，直接使用它的 y 坐标
        return int(round(float(y_centers[0])))


def get_solid_fill_color(im0_bgr: np.ndarray, mode: str = "background") -> tuple[int, int, int]:
    """
    获取遮盖用的纯色 (B, G, R)。
    - background: 用图像整体均值颜色（更贴近背景）
    - white/black: 纯白/纯黑
    """
    mode = (mode or "background").lower()
    if mode == "white":
        return (255, 255, 255)
    if mode == "black":
        return (0, 0, 0)
    # background
    b, g, r, _ = cv2.mean(im0_bgr)
    return (int(round(b)), int(round(g)), int(round(r)))


def mask_outside_band(
    im0_bgr: np.ndarray,
    boxes_xyxy: np.ndarray,
    y_ref: int,
    y_tolerance: int,
    pad: int = 6,
    color_mode: str = "background",
    x_limit: int | None = None,
) -> np.ndarray:
    """
    在"筛选斑点之前"先做一次**整行遮盖**：
    - 仅保留 [y_ref - y_tolerance, y_ref + y_tolerance] 这一水平带上的信息
    - 该带之外的整行像素全部用纯色覆盖，从根源上去掉上下干扰斑点
    - 与检测框无关，避免"先用框再筛选"导致漏点

    为了兼容旧接口，这里仍保留 boxes_xyxy 和 x_limit 参数，但当前实现不再依赖它们。
    """
    if im0_bgr is None or y_ref is None:
        return im0_bgr

    h, w = im0_bgr.shape[:2]
    fill = get_solid_fill_color(im0_bgr, color_mode)
    out = im0_bgr.copy()

    band_half = max(int(y_tolerance), 0)
    y_center = int(y_ref)
    y1_band = max(0, y_center - band_half)
    y2_band = min(h, y_center + band_half)

    # 覆盖 band 之上的所有行
    if y1_band > 0:
        out[0:y1_band, :] = fill

    # 覆盖 band 之下的所有行
    if y2_band < h:
        out[y2_band:h, :] = fill

    return out


def preprocess_im0_for_model(im0_bgr: np.ndarray, img_size, stride: int, auto: bool):
    """
    将 im0(BGR) 按 YOLOv5 的 LoadImages 逻辑 letterbox + BGR->RGB + HWC->CHW。
    返回: (im_chw_rgb_contiguous, im_letterbox_bgr)
    """
    im_lb = letterbox(im0_bgr, img_size, stride=stride, auto=auto)[0]  # padded resize (BGR)
    im = im_lb.transpose((2, 0, 1))[::-1]  # HWC to CHW, BGR to RGB
    im = np.ascontiguousarray(im)
    return im, im_lb


def rect_from_center(cx, cy, fw, fh, img_w, img_h):
    """以中心点生成固定大小矩形，并限制在图像范围内。"""
    x1 = int(cx - fw // 2)
    y1 = int(cy - fh // 2)
    x2 = x1 + int(fw)
    y2 = y1 + int(fh)
    if x1 < 0:
        x2 -= x1
        x1 = 0
    if y1 < 0:
        y2 -= y1
        y1 = 0
    if x2 > img_w:
        shift = x2 - img_w
        x1 = max(0, x1 - shift)
        x2 = img_w
    if y2 > img_h:
        shift = y2 - img_h
        y1 = max(0, y1 - shift)
        y2 = img_h
    return [x1, y1, x2, y2]


def _rect_hit_test(rect, x, y, margin=6):
    x1, y1, x2, y2 = rect
    return (x1 - margin) <= x <= (x2 + margin) and (y1 - margin) <= y <= (y2 + margin)


def _manual_mark_help_canvas(box_count: int) -> np.ndarray:
    """Fixed-size help panel (not drawn on the TLC image, so it will not stretch)."""
    canvas = np.full((300, 720, 3), 32, dtype=np.uint8)
    lines = [
        ("MANUAL MARK - how to edit boxes", (255, 255, 255), 0.85, 2),
        ("Green AUTO = already detected", (200, 200, 200), 0.65, 1),
        ("", (0, 0, 0), 0.5, 1),
        ("Left-click  =  ADD box", (220, 220, 220), 0.75, 2),
        ("Right-click =  DELETE box", (220, 220, 220), 0.75, 2),
        ("", (0, 0, 0), 0.5, 1),
        ("NEXT: press S to save and continue", (0, 255, 255), 0.78, 2),
        ("Esc = skip (keep auto only)", (180, 180, 255), 0.65, 1),
        ("", (0, 0, 0), 0.5, 1),
        (f"Manual boxes added: {box_count}", (160, 255, 160), 0.7, 2),
        ("Click the IMAGE window, then use mouse / keys", (170, 170, 170), 0.55, 1),
    ]
    y = 36
    for text, color, scale, thickness in lines:
        if text:
            cv2.putText(canvas, text, (24, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)
        y += 28 if text else 12
    cv2.rectangle(canvas, (8, 8), (711, 291), (0, 200, 255), 2)
    return canvas


def select_manual_rectangles(
        image_bgr: np.ndarray,
        window_name: str = "Manual Mark Spots",
        fixed_width: int = 130,
        fixed_height: int = 35,
) -> list[list[int]]:
    """
    Manual marking: box size matches auto detection (fixed_width x fixed_height).
    Controls:
    - Left-click: add a fixed-size box centred on the click
    - Right-click: delete a box (or undo last if clicking empty area)
    - Left-drag a yellow box: move it
    - Delete / D: delete selected box
    - S: save and continue to the next image
    - ESC: skip manual boxes for this image
    """
    if image_bgr is None or image_bgr.size == 0:
        return []

    h, w = image_bgr.shape[:2]
    base = image_bgr.copy()
    rectangles: list[list[int]] = []
    state = {
        "selected": -1,
        "dragging": False,
        "drag_offset_x": 0,
        "drag_offset_y": 0,
        "hover": None,
    }
    help_window = "Manual Mark - Help"

    def clamp_point(x, y):
        return max(0, min(x, w - 1)), max(0, min(y, h - 1))

    def find_rect_at(x, y):
        for idx in range(len(rectangles) - 1, -1, -1):
            if _rect_hit_test(rectangles[idx], x, y):
                return idx
        return -1

    def on_mouse(event, x, y, flags, param):
        x, y = clamp_point(x, y)
        if event == cv2.EVENT_MOUSEMOVE:
            state["hover"] = (x, y)
            if state["dragging"] and state["selected"] >= 0:
                cx = x - state["drag_offset_x"]
                cy = y - state["drag_offset_y"]
                rectangles[state["selected"]] = rect_from_center(cx, cy, fixed_width, fixed_height, w, h)
        elif event == cv2.EVENT_LBUTTONDOWN:
            hit = find_rect_at(x, y)
            if hit >= 0:
                state["selected"] = hit
                rcx = (rectangles[hit][0] + rectangles[hit][2]) // 2
                rcy = (rectangles[hit][1] + rectangles[hit][3]) // 2
                state["drag_offset_x"] = x - rcx
                state["drag_offset_y"] = y - rcy
                state["dragging"] = True
            else:
                rectangles.append(rect_from_center(x, y, fixed_width, fixed_height, w, h))
                state["selected"] = len(rectangles) - 1
        elif event == cv2.EVENT_LBUTTONUP:
            state["dragging"] = False
        elif event == cv2.EVENT_RBUTTONDOWN:
            hit = find_rect_at(x, y)
            if hit >= 0:
                rectangles.pop(hit)
                if state["selected"] == hit:
                    state["selected"] = -1
                elif state["selected"] > hit:
                    state["selected"] -= 1
            elif rectangles:
                rectangles.pop()
                state["selected"] = min(state["selected"], len(rectangles) - 1)

    def _draw_status_bar(canvas: np.ndarray) -> None:
        # Short bar only - font scales with image width so it stays readable
        scale = float(np.clip(w / 1100.0, 0.7, 1.6))
        thickness = 2 if scale < 1.1 else 3
        bar_h = int(42 * scale)
        overlay = canvas.copy()
        cv2.rectangle(overlay, (0, 0), (w - 1, bar_h), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.65, canvas, 0.35, 0, canvas)
        text = f"Left=ADD   Right=DELETE   S=NEXT   Esc=SKIP   (+{len(rectangles)})"
        cv2.putText(
            canvas, text, (12, int(28 * scale)),
            cv2.FONT_HERSHEY_SIMPLEX, scale * 0.7, (0, 255, 255), thickness, cv2.LINE_AA,
        )

    # Help window: fixed pixel size, AUTOSIZE so text is never stretched
    cv2.namedWindow(help_window, cv2.WINDOW_AUTOSIZE)
    cv2.imshow(help_window, _manual_mark_help_canvas(0))

    # Image window: keep aspect ratio when fitting to screen
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    fit = min(1280 / max(w, 1), 720 / max(h, 1), 1.0)
    cv2.resizeWindow(window_name, max(400, int(w * fit)), max(240, int(h * fit)))
    cv2.setMouseCallback(window_name, on_mouse)

    print(
        "\n===== Manual Mark =====\n"
        f"Image window: {window_name}\n"
        "Help window : Manual Mark - Help  (keep it open; text will not stretch)\n"
        "  Left-click  = ADD box\n"
        "  Right-click = DELETE box\n"
        "  S           = SAVE and go to NEXT image\n"
        "  Esc         = SKIP manual boxes for this image\n"
        "========================\n"
    )

    while True:
        canvas = base.copy()
        for idx, (x1, y1, x2, y2) in enumerate(rectangles):
            color = (0, 255, 255) if idx == state["selected"] else (0, 200, 255)
            thickness = 3 if idx == state["selected"] else 2
            cv2.rectangle(canvas, (x1, y1), (x2, y2), color, thickness)
            cv2.putText(canvas, f"M{idx + 1}", (x1, max(15, y1 - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        if state["hover"] and state["selected"] < 0 and not state["dragging"]:
            hx, hy = state["hover"]
            if find_rect_at(hx, hy) < 0:
                px1, py1, px2, py2 = rect_from_center(hx, hy, fixed_width, fixed_height, w, h)
                cv2.rectangle(canvas, (px1, py1), (px2, py2), (255, 255, 0), 1)

        _draw_status_bar(canvas)
        cv2.imshow(window_name, canvas)
        cv2.imshow(help_window, _manual_mark_help_canvas(len(rectangles)))

        key = cv2.waitKey(20) & 0xFF
        if key in (ord("s"), ord("S")):
            break
        if key in (8, 127, ord("d"), ord("D")):
            if 0 <= state["selected"] < len(rectangles):
                rectangles.pop(state["selected"])
                state["selected"] = -1
            elif rectangles:
                rectangles.pop()
        if key == 27:
            rectangles = []
            break

    cv2.setMouseCallback(window_name, lambda *args: None)
    for name in (window_name, help_window):
        try:
            cv2.destroyWindow(name)
        except Exception:
            pass
    return [rect_from_center(
        (r[0] + r[2]) // 2, (r[1] + r[3]) // 2, fixed_width, fixed_height, w, h
    ) for r in rectangles]


def process_manual_rectangles(gray_im, color_im, manual_rects, start_spot_idx=0, fixed_width=130, fixed_height=35):
    """将手动矩形转换为和自动检测一致的特征结果（固定 ROI 大小）。"""
    if gray_im is None or color_im is None:
        return []
    h, w = gray_im.shape[:2]
    global_mean_bg = float(np.median(gray_im)) if gray_im.size > 0 else 1.0

    prepared = []
    for i, rect in enumerate(manual_rects):
        cx = (int(rect[0]) + int(rect[2])) // 2
        cy = (int(rect[1]) + int(rect[3])) // 2
        x1, y1, x2, y2 = rect_from_center(cx, cy, fixed_width, fixed_height, w, h)
        if x2 <= x1 or y2 <= y1:
            continue
        roi_gray = gray_im[y1:y2, x1:x2]
        roi_color = color_im[y1:y2, x1:x2]
        if roi_gray.size == 0:
            continue
        prepared.append({
            "i": i, "cx": cx, "cy": cy, "box": [x1, y1, x2, y2],
            "roi_gray": roi_gray, "roi_color": roi_color,
            "mean_fg": float(roi_gray.mean()),
        })

    lane_bg = estimate_lane_background(gray_im, [p["box"] for p in prepared])
    polarity = detect_signal_polarity([p["mean_fg"] for p in prepared], lane_bg)
    results = []
    for item in prepared:
        i, cx, cy = item["i"], item["cx"], item["cy"]
        x1, y1, x2, y2 = item["box"]
        roi_gray, roi_color = item["roi_gray"], item["roi_color"]
        mean_fg = item["mean_fg"]
        sum_gray = int(roi_gray.sum())

        local_bg = calculate_local_background(gray_im, [x1, y1, x2, y2], margin=15)
        bg_use = lane_bg
        sum_gray_corrected, mean_gray_corrected, _ = compute_net_integral(
            roi_gray, bg_use, None, polarity=polarity
        )
        sum_od, mean_od = compute_masked_od(roi_gray, bg_use, None)
        sum_od_global, mean_od_global = compute_masked_od(roi_gray, global_mean_bg, None)
        sum_od_local, mean_od_local = compute_masked_od(roi_gray, local_bg, None)
        od_method = "lane_shared"

        if roi_color.size > 0:
            avg_B = np.mean(roi_color[:, :, 0])
            avg_G = np.mean(roi_color[:, :, 1])
            avg_R = np.mean(roi_color[:, :, 2])
            hsv_roi = cv2.cvtColor(roi_color, cv2.COLOR_BGR2HSV)
            avg_H = np.mean(hsv_roi[:, :, 0])
            avg_S = np.mean(hsv_roi[:, :, 1])
            avg_V = np.mean(hsv_roi[:, :, 2])
            lab_roi = cv2.cvtColor(roi_color, cv2.COLOR_BGR2Lab)
            avg_L = np.mean(lab_roi[:, :, 0])
            avg_A = np.mean(lab_roi[:, :, 1])
            avg_B_lab = np.mean(lab_roi[:, :, 2])
            C_map = np.sqrt(lab_roi[:, :, 1].astype(float) ** 2 + lab_roi[:, :, 2].astype(float) ** 2)
            avg_C = np.mean(C_map)
        else:
            avg_R, avg_G, avg_B = 0, 0, 0
            avg_H, avg_S, avg_V = 0, 0, 0
            avg_L, avg_A, avg_B_lab, avg_C = 0, 0, 0, 0

        ratio_local = mean_fg / local_bg if local_bg > 0 else 0
        ratio_global = mean_fg / global_mean_bg if global_mean_bg > 0 else 0
        ratio_lane = mean_fg / bg_use if bg_use > 0 else 0
        results.append({
            "Image": "",
            "Spot_Index": start_spot_idx + i,
            "Original_Index": -1,
            "X_Position": cx,
            "Y_Position": cy,
            "Width": int(fixed_width),
            "Height": int(fixed_height),
            "Area": int(fixed_width * fixed_height),
            "Mean_Gray": round(float(mean_fg), 2),
            "Sum_Gray": sum_gray,
            "Sum_Gray_Corrected": round(float(sum_gray_corrected), 2),
            "Mean_Gray_Corrected": round(float(mean_gray_corrected), 2),
            "Net_Signal": round(float(sum_gray_corrected), 2),
            "Signal_Polarity": polarity,
            "Lane_Background": round(float(bg_use), 2),
            "Mean_OD": round(float(mean_od), 4),
            "Sum_OD": round(float(sum_od), 4),
            "Mean_OD_Global": round(float(mean_od_global), 4),
            "Sum_OD_Global": round(float(sum_od_global), 4),
            "Mean_OD_Local": round(float(mean_od_local), 4),
            "Sum_OD_Local": round(float(sum_od_local), 4),
            "OD_Method": od_method,
            "IOD": round(float(sum_od_global), 4),
            "Peak_Area": 0.0,
            "Baseline_Peak": round(float(bg_use), 2),
            "Global_Background": round(float(global_mean_bg), 2),
            "Local_Background": round(float(local_bg), 2),
            "Gray_Ratio_Global": round(float(ratio_global), 4),
            "Gray_Ratio_Local": round(float(ratio_local), 4),
            "Gray_Ratio_Lane": round(float(ratio_lane), 4),
            "Center_Point": f"{cx},{cy}",
            "R": round(float(avg_R), 2),
            "G": round(float(avg_G), 2),
            "B": round(float(avg_B), 2),
            "H": round(float(avg_H), 2),
            "S": round(float(avg_S), 2),
            "V": round(float(avg_V), 2),
            "L": round(float(avg_L), 2),
            "A": round(float(avg_A), 2),
            "B_lab": round(float(avg_B_lab), 2),
            "C": round(float(avg_C), 2),
            "Spot_Type": "",
            "Known_Concentration": None,
            "Calculated_Concentration": None,
            "Spot_Source": "manual",
            "Manual_Rect": f"{x1},{y1},{x2},{y2}",
        })
    return results


def calculate_optical_density(gray_im, global_bg):
    """
    计算光密度值 - 修正版本
    OD = log10(背景强度 / 样品强度)
    """
    # 确保输入有效
    if gray_im.size == 0 or global_bg <= 0:
        return np.zeros_like(gray_im, dtype=float)

    # 将图像转换为浮点数
    gray_im_float = gray_im.astype(float)

    # 避免除零错误 - 将零值设为很小的正数
    gray_im_float[gray_im_float == 0] = 1e-10

    # 避免背景为零
    if global_bg <= 0:
        global_bg = 1e-10

    # 计算光密度
    try:
        od_map = np.log10(global_bg / gray_im_float)

        # 检查异常值
        if np.any(np.isnan(od_map)) or np.any(np.isinf(od_map)):
            print("Warning: OD calculation produced invalid values")
            # 将异常值设为0
            od_map = np.nan_to_num(od_map, nan=0.0, posinf=0.0, neginf=0.0)

        # 将负值设为0（物理上不可能为负）
        od_map[od_map < 0] = 0

        return od_map
    except Exception as e:
        print(f"OD calculation error: {e}")
        return np.zeros_like(gray_im_float)


def analyze_image_statistics(gray_im, color_im):
    """
    分析图像统计信息，帮助诊断问题
    """
    print("\n=== Image statistics ===")
    print(f"Image shape: {gray_im.shape}")
    print(f"Gray range: [{gray_im.min()}, {gray_im.max()}]")
    print(f"Gray mean: {gray_im.mean():.2f}")
    print(f"Gray std dev: {gray_im.std():.2f}")

    # 检查是否有异常值
    unique_vals = np.unique(gray_im)
    print(f"Unique gray levels: {len(unique_vals)}")
    print(f"First 10 unique values: {unique_vals[:10]}")

    # 检查彩色图像统计
    if color_im is not None:
        print(f"Color image shape: {color_im.shape}")
        print(f"R channel range: [{color_im[:, :, 0].min()}, {color_im[:, :, 0].max()}]")
        print(f"G channel range: [{color_im[:, :, 1].min()}, {color_im[:, :, 1].max()}]")
        print(f"B channel range: [{color_im[:, :, 2].min()}, {color_im[:, :, 2].max()}]")

    # 检查图像是否过暗或过亮
    if gray_im.mean() < 30:
        print("Warning: image may be underexposed")
    elif gray_im.mean() > 220:
        print("Warning: image may be overexposed")

    print("==================\n")


def detect_background_type(color_im: np.ndarray) -> str:
    """
    检测图像背景类型。
    - 蓝色背景：返回 'blue'
    - 其他颜色背景（白/绿等）：返回 'other'
    """
    if color_im is None or color_im.size == 0:
        return "other"

    h, w = color_im.shape[:2]
    margin = max(8, min(h, w) // 12)
    strips = [
        color_im[:margin, :],
        color_im[-margin:, :],
        color_im[:, :margin],
        color_im[:, -margin:],
    ]
    bg_pixels = np.vstack([s.reshape(-1, 3) for s in strips if s.size > 0]).astype(np.float32)
    if bg_pixels.size == 0:
        return "other"

    mean_b, mean_g, mean_r = bg_pixels.mean(axis=0)
    hsv = cv2.cvtColor(bg_pixels.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_BGR2HSV).reshape(-1, 3)
    mean_h, mean_s, mean_v = hsv.mean(axis=0)

    blue_by_channel = mean_b > mean_r + 12 and mean_b > mean_g + 8 and mean_b > 80
    blue_by_hue = 90 <= mean_h <= 135 and mean_s > 35 and mean_v > 35
    if blue_by_channel or blue_by_hue:
        return "blue"
    return "other"


def get_calibration_y_axis_for_background(background_type: str) -> tuple[str, str]:
    """按论文策略：366 nm 荧光板用 IGI，可见光/254 nm 用 IOD。"""
    if background_type == "blue":
        return "sum_gray", "IGI (gray integral)"
    return "sum_od", "IOD (total optical density)"


def _is_degenerate_response(vals) -> tuple[bool, float, float]:
    """判断响应序列是否退化（大量为 0 或几乎无动态范围）。"""
    vals = np.asarray(vals, dtype=float)
    if vals.size < 2:
        return True, 0.0, 0.0
    nonzero_ratio = float(np.mean(np.abs(vals) > 1e-9))
    dyn = float(np.ptp(vals))
    scale = float(np.median(np.abs(vals[np.abs(vals) > 1e-9]))) if nonzero_ratio > 0 else 0.0
    degenerate = nonzero_ratio < 0.6 or dyn <= max(1e-6, 0.01 * scale)
    return degenerate, nonzero_ratio, dyn


def resolve_imaging_profile(imaging_mode: str, color_im: np.ndarray) -> str:
    """确定背景类型：blue=366nm 荧光板，other=可见光/254nm 吸收板。"""
    try:
        from utils.load_user_config import normalize_imaging_mode
        mode = normalize_imaging_mode(imaging_mode)
    except Exception:
        mode = str(imaging_mode or "auto").strip().lower()

    if mode == "366nm":
        return "blue"
    if mode in ("visible", "254nm"):
        return "other"
    return detect_background_type(color_im)


def _spearman_abs(conc, vals) -> float:
    """浓度与响应的 |Spearman|，无效时返回 0。"""
    conc = np.asarray(conc, dtype=float)
    vals = np.asarray(vals, dtype=float)
    if conc.size < 2 or vals.size < 2 or conc.size != vals.size:
        return 0.0
    try:
        rho = abs(float(stats.spearmanr(conc, vals).correlation))
    except Exception:
        return 0.0
    return rho if np.isfinite(rho) else 0.0


def select_paper_response_axis(
    standard_results,
    concentrations,
    background_type: str,
) -> tuple[str, str, str, float]:
    """
    论文优先的响应指标选择：
    - 366nm/blue：默认 IGI(sum_gray)；若 IGI 退化，或 IGI 单调性差于 peak_1d，则备选 peak_1d
    - 可见光/254nm/other：固定 IOD(sum_od)
    返回: y_axis_type, y_label, axis_source, |spearman|
    """
    conc = np.asarray(concentrations, dtype=float)
    mono_threshold = 0.5
    mono_margin = 0.05

    if background_type == "blue":
        igi_vals = np.asarray([_extract_y_value(r, "sum_gray") for r in standard_results], dtype=float)
        peak_vals = np.asarray([_extract_y_value(r, "peak_1d") for r in standard_results], dtype=float)
        igi_deg, nz, dyn = _is_degenerate_response(igi_vals)
        peak_deg, peak_nz, peak_dyn = _is_degenerate_response(peak_vals)
        igi_sp = _spearman_abs(conc, igi_vals)
        peak_sp = _spearman_abs(conc, peak_vals)

        use_peak = False
        axis_source = "igi"
        reason = ""

        if igi_deg and not peak_deg:
            use_peak = True
            axis_source = "peak_1d_fallback"
            reason = (
                f"IGI degraded (nonzero={nz:.2f}, dynamic range={dyn:.4g}); "
                f"peak_1d usable (nonzero={peak_nz:.2f}, dynamic range={peak_dyn:.4g})"
            )
        elif (
            not peak_deg
            and igi_sp < mono_threshold
            and peak_sp >= mono_threshold
            and peak_sp > igi_sp + mono_margin
        ):
            use_peak = True
            axis_source = "peak_1d_fallback"
            reason = (
                f"IGI weak monotonicity (|Spearman|={igi_sp:.2f}<{mono_threshold}); "
                f"peak_1d better (|Spearman|={peak_sp:.2f})"
            )
        elif igi_deg and peak_deg:
            axis_source = "igi_degraded"
            print("[Warning] Both IGI and peak_1d degraded; keeping IGI")

        if use_peak:
            y_axis_type, y_label = "peak_1d", "1D peak area (366 nm fallback)"
            print(f"[366nm fallback] {reason}; using peak_1d")
            LOGGER.warning(f"366nm fallback to peak_1d: {reason}")
        else:
            y_axis_type, y_label = "sum_gray", "IGI (gray integral)"
    else:
        y_axis_type, y_label = "sum_od", "IOD (total optical density)"
        axis_source = "iod"

    vals = np.asarray([_extract_y_value(r, y_axis_type) for r in standard_results], dtype=float)
    spearman_abs = _spearman_abs(conc, vals)

    return y_axis_type, y_label, axis_source, spearman_abs


def compute_gray_integral(gray_roi: np.ndarray, local_bg: float, mask_roi: np.ndarray | None = None,
                          polarity: str = "auto") -> tuple[float, float]:
    """
    计算背景校正后的净信号积分（兼容旧接口）。
    荧光板：I-bg；吸收板：bg-I。有 mask 时只统计斑点像素。
    """
    net_sum, net_mean, _ = compute_net_integral(gray_roi, local_bg, mask_roi, polarity=polarity)
    return net_sum, net_mean


def _extract_y_value(result: dict, y_axis_type: str) -> float:
    if y_axis_type == "peak_1d":
        return float(result.get("Peak_Area_1D", result.get("Net_Signal", 0.0)))
    if y_axis_type == "net_signal":
        return float(result.get("Net_Signal", result.get("Sum_Gray_Corrected", result.get("Sum_Gray", 0.0))))
    if y_axis_type == "sum_gray":
        return float(result.get("Sum_Gray_Corrected", result.get("Net_Signal", result.get("Sum_Gray", 0.0))))
    if y_axis_type == "mean_gray":
        return float(result.get("Mean_Gray_Corrected", result.get("Mean_Gray", 0.0)))
    if y_axis_type == "sum_od":
        return float(result.get("Sum_OD", 0.0))
    if y_axis_type == "mean_od":
        return float(result.get("Mean_OD", 0.0))
    return float(result.get("Net_Signal", result.get("Sum_Gray", 0.0)))


def select_best_response_axis(standard_results, concentrations,
                              background_type: str = "other") -> tuple[str, str, float]:
    """
    按板类型选定量指标（优先保证数据可用）：
    - 蓝色/366nm 荧光板：只在灰度类里选（一维峰面积、净信号、灰度积分），不用光密度
    - 其他颜色吸收板：优先光密度，必要时再用净信号/一维峰面积
    会跳过“几乎全是 0 / 几乎无变化”的退化指标。
    返回: (y_axis_type, 中文标签, |spearman|)
    """
    if background_type == "blue":
        candidates = [
            ("peak_1d", "1D peak area"),
            ("net_signal", "Net signal (lane background subtracted)"),
            ("sum_gray", "Gray integral (background subtracted)"),
        ]
        fallback_key, fallback_label = "net_signal", "Net signal (lane background subtracted)"
    else:
        candidates = [
            ("sum_od", "Total OD (within mask)"),
            ("peak_1d", "1D peak area"),
            ("net_signal", "Net signal (lane background subtracted)"),
            ("mean_gray", "Mean gray (background subtracted)"),
        ]
        fallback_key, fallback_label = "sum_od", "Total OD (within mask)"

    conc = np.asarray(concentrations, dtype=float)
    best_key, best_label, best_score = fallback_key, fallback_label, -1.0
    scored = []

    for key, label in candidates:
        vals = np.asarray([_extract_y_value(r, key) for r in standard_results], dtype=float)
        if vals.size < 2:
            continue
        # 退化指标：大半为 0，或几乎无动态范围 → 样品会全部预测成同一个浓度
        nonzero_ratio = float(np.mean(np.abs(vals) > 1e-9))
        dyn = float(np.ptp(vals))
        scale = float(np.median(np.abs(vals[np.abs(vals) > 1e-9]))) if nonzero_ratio > 0 else 0.0
        if nonzero_ratio < 0.6 or dyn <= max(1e-6, 0.01 * scale):
            print(f"[Skip degenerate axis] {label}: nonzero={nonzero_ratio:.2f}, dynamic range={dyn:.4g}")
            continue
        try:
            corr = float(stats.spearmanr(conc, vals).correlation)
        except Exception:
            corr = 0.0
        if not np.isfinite(corr):
            corr = 0.0
        score = abs(corr)
        scored.append((score, key, label, corr, vals))
        if score > best_score:
            best_key, best_label, best_score = key, label, score

    if scored:
        scored.sort(reverse=True, key=lambda x: x[0])
        print(f"Response axis scores (plate={background_type}, high to low):")
        for score, key, label, corr, vals in scored[:5]:
            print(f"  {label}: |Spearman|={score:.3f} (r={corr:.3f}), values={np.round(vals, 1).tolist()}")
    else:
        print(f"[Warning] All candidates degenerate; fallback: {fallback_label}")

    return best_key, best_label, best_score


def calculate_calibration_curve_quadratic(standard_results, standard_concentrations, y_axis_type="sum_od",
                                          y_label: str | None = None,
                                          quantification_method: str = "isotonic"):
    """
    稳健标准曲线：
    1) 检查左右浓度顺序是否反了（Spearman）
    2) 用等单调回归保证 响应→浓度 单调
    3) 同时保留二次拟合用于绘图/对照
    """
    if len(standard_results) != len(standard_concentrations):
        raise ValueError("Standard count does not match concentration list length")
    if len(standard_results) < 3:
        raise ValueError("Quadratic fit requires at least 3 standard points")

    if y_label is None:
        _, y_label = get_calibration_y_axis_for_background(
            "blue" if y_axis_type in ("sum_gray", "net_signal") else "other"
        )

    concentrations = np.array(standard_concentrations, dtype=float)
    y_values = np.array([_extract_y_value(r, y_axis_type) for r in standard_results], dtype=float)

    # 左右顺序检查：若反序相关性明显更好，自动翻转浓度匹配
    order_reversed = False
    try:
        spearman_fwd = float(stats.spearmanr(concentrations, y_values).correlation)
        spearman_rev = float(stats.spearmanr(concentrations[::-1], y_values).correlation)
    except Exception:
        spearman_fwd, spearman_rev = 0.0, 0.0
    if not np.isfinite(spearman_fwd):
        spearman_fwd = 0.0
    if not np.isfinite(spearman_rev):
        spearman_rev = 0.0

    if spearman_rev > 0.65 and spearman_fwd < 0.35 and (spearman_rev - spearman_fwd) > 0.35:
        concentrations = concentrations[::-1].copy()
        order_reversed = True
        print(
            f"[Warning] Standard concentration order may be reversed: "
            f"forward Spearman={spearman_fwd:.3f}, reversed={spearman_rev:.3f}. Auto-matched concentrations right-to-left."
        )
        for i, result in enumerate(standard_results):
            result["Known_Concentration"] = float(concentrations[i])
            result["Concentration_Order_Reversed"] = True
    else:
        print(f"Standard monotonicity: Spearman(conc, response)={spearman_fwd:.3f}")

    # 二次拟合（原始点）
    coefs = np.polyfit(concentrations, y_values, deg=2)  # [a, b, c]
    y_pred = np.polyval(coefs, concentrations)
    r_squared = float(r2_score(y_values, y_pred)) if len(np.unique(y_values)) > 1 else 0.0

    spearman_used = spearman_rev if order_reversed else spearman_fwd
    increasing = bool(spearman_used >= 0)

    # 等单调：响应 -> 浓度（提高定量稳定性）
    iso = IsotonicRegression(increasing=increasing, out_of_bounds="clip")
    try:
        iso.fit(y_values, concentrations)
        iso_pred = iso.predict(y_values)
        iso_r2 = float(r2_score(concentrations, iso_pred)) if len(np.unique(concentrations)) > 1 else 0.0
    except Exception as e:
        print(f"Isotonic regression failed; fallback to quadratic: {e}")
        iso = None
        iso_r2 = -1.0

    # 对响应做等单调平滑后再拟合二次，用于绘图更“顺”
    iso_y = IsotonicRegression(increasing=increasing, out_of_bounds="clip")
    try:
        y_mono = iso_y.fit_transform(concentrations, y_values)
        coefs_mono = np.polyfit(concentrations, y_mono, deg=2)
        r2_mono = float(r2_score(y_mono, np.polyval(coefs_mono, concentrations)))
    except Exception:
        y_mono = y_values
        coefs_mono = coefs
        r2_mono = r_squared

    use_isotonic = iso is not None and (
        iso_r2 >= r_squared or r_squared < 0.75 or abs(spearman_used) < 0.8
    )

    method = str(quantification_method or "isotonic").strip().lower()
    if method == "quadratic":
        use_isotonic = False
    elif method == "isotonic":
        use_isotonic = iso is not None

    calibration_params = {
        "fit_type": "isotonic+quadratic" if use_isotonic else "quadratic",
        "quantification_method": "isotonic" if use_isotonic else "quadratic",
        "coefs": coefs.tolist(),
        "coefs_mono": coefs_mono.tolist(),
        "a": float(coefs[0]),
        "b": float(coefs[1]),
        "c": float(coefs[2]),
        "r_squared": float(r_squared),
        "r_squared_isotonic": float(iso_r2),
        "r_squared_mono_curve": float(r2_mono),
        "y_axis_type": y_axis_type,
        "y_label": y_label,
        "x_label": "Concentration",
        "background_type": "blue" if y_axis_type in ("sum_gray", "net_signal") else "other",
        "X_original": concentrations.tolist(),
        "y_original": y_values.tolist(),
        "y_monotonic": y_mono.tolist() if hasattr(y_mono, "tolist") else list(y_mono),
        "conc_min": float(concentrations.min()),
        "conc_max": float(concentrations.max()),
        "y_min": float(y_values.min()),
        "y_max": float(y_values.max()),
        "spearman": float(spearman_fwd if not order_reversed else spearman_rev),
        "order_reversed": order_reversed,
        "use_isotonic": use_isotonic,
        "isotonic_model": iso if use_isotonic else None,
    }
    return calibration_params, float(r_squared)


def _range_tolerance(base: float, rel: float = 1e-4, abs_tol: float = 1e-9) -> float:
    return max(abs_tol, abs(float(base)) * rel)


def _response_bounds_from_standards(ys) -> tuple[float, float]:
    ys = np.asarray(ys, dtype=float)
    if ys.size == 0:
        return 0.0, 0.0
    return float(np.min(ys)), float(np.max(ys))


def assess_sample_quantification_range(y_value: float, conc: float, calibration_params: dict) -> dict:
    """
    判断样品响应/反算浓度是否落在标准品建立的验证范围内。
    超出时标记 Out_of_Range，并说明是否为 clip 到端点浓度。
    """
    ys = np.asarray(calibration_params.get("y_original", []), dtype=float)
    cmin = float(calibration_params.get("conc_min", 0.0))
    cmax = float(calibration_params.get("conc_max", 1.0))
    y_lo = float(calibration_params.get("y_min", np.min(ys) if ys.size else 0.0))
    y_hi = float(calibration_params.get("y_max", np.max(ys) if ys.size else 0.0))
    conc = float(max(0.0, conc))

    resp_below = ys.size > 0 and y_value < y_lo - _range_tolerance(y_lo)
    resp_above = ys.size > 0 and y_value > y_hi + _range_tolerance(y_hi)
    conc_below = conc < cmin - _range_tolerance(cmin)
    conc_above = conc > cmax + _range_tolerance(cmax)

    clipped_low = resp_below and abs(conc - cmin) <= _range_tolerance(cmin, rel=0.02)
    clipped_high = resp_above and abs(conc - cmax) <= _range_tolerance(cmax, rel=0.02)

    reasons: list[str] = []
    if resp_below:
        reasons.append("response_below_standards")
    if resp_above:
        reasons.append("response_above_standards")
    if conc_below:
        reasons.append("concentration_below_range")
    if conc_above:
        reasons.append("concentration_above_range")
    if clipped_low:
        reasons.append("clipped_to_min")
    if clipped_high:
        reasons.append("clipped_to_max")

    in_range = not reasons
    return {
        "Out_of_Range": not in_range,
        "Range_Status": "in_range" if in_range else ";".join(reasons),
        "Response_In_Range": not (resp_below or resp_above),
        "Concentration_In_Range": not (conc_below or conc_above),
        "Calibration_Y_Min": y_lo,
        "Calibration_Y_Max": y_hi,
        "Calibration_Conc_Min": cmin,
        "Calibration_Conc_Max": cmax,
    }


def _interp_concentration_from_standards(y_value: float, xs, ys) -> float:
    """
    稳健回退：用标准品响应值 -> 浓度 的邻近加权估计。
    不依赖曲线单调；超出标准品响应范围时夹到端点浓度，避免直接给 0。
    """
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    if xs.size == 0:
        return 0.0
    if xs.size == 1:
        return float(max(0.0, xs[0]))

    order = np.argsort(ys)
    ys_s = ys[order]
    xs_s = xs[order]

    # 相同响应值合并，避免插值抖动
    uniq_y, inv = np.unique(ys_s, return_inverse=True)
    uniq_x = np.zeros_like(uniq_y)
    for i in range(len(uniq_y)):
        uniq_x[i] = float(np.mean(xs_s[inv == i]))

    if y_value <= uniq_y[0]:
        return float(max(0.0, uniq_x[0]))
    if y_value >= uniq_y[-1]:
        return float(max(0.0, uniq_x[-1]))

    # 响应基本单调时用插值；否则用最近邻加权
    mono_inc = np.all(np.diff(uniq_x) >= -1e-12)
    mono_dec = np.all(np.diff(uniq_x) <= 1e-12)
    if mono_inc or mono_dec:
        return float(max(0.0, np.interp(y_value, uniq_y, uniq_x)))

    dists = np.abs(ys - y_value)
    k = min(3, len(ys))
    idx = np.argpartition(dists, k - 1)[:k]
    weights = 1.0 / (dists[idx] + 1e-12)
    return float(max(0.0, np.average(xs[idx], weights=weights)))


def _project_concentration_on_quadratic(y_value: float, a: float, b: float, c: float,
                                         cmin: float, cmax: float) -> float:
    """无实根时，在浓度区间上找使二次曲线最接近 y_value 的浓度。"""
    hi = max(cmax * 3.0, cmin + 1e-9, 1e-9)
    x_grid = np.linspace(0.0, hi, 800)
    y_grid = a * x_grid ** 2 + b * x_grid + c
    return float(max(0.0, x_grid[int(np.argmin(np.abs(y_grid - y_value)))]))


def solve_concentration_from_quadratic(y_value: float, calibration_params: dict) -> float:
    """
    由二次曲线反解浓度。
    判别式为负、无正根、或非单调导致反解异常时，回退到标准品邻近估计，避免样品浓度被硬写成 0。
    """
    a = float(calibration_params["a"])
    b = float(calibration_params["b"])
    c = float(calibration_params["c"])
    cmin = float(calibration_params.get("conc_min", 0.0))
    cmax = float(calibration_params.get("conc_max", 1.0))
    xs = calibration_params.get("X_original", [])
    ys = calibration_params.get("y_original", [])
    fallback = _interp_concentration_from_standards(y_value, xs, ys)

    if abs(a) < 1e-12:
        if abs(b) > 1e-12:
            conc = float((y_value - c) / b)
            if conc >= 0:
                return conc
        return fallback

    discriminant = b * b - 4 * a * (c - y_value)
    if discriminant < 0:
        # 样品响应落在抛物线开口外：投影到曲线最近点，再与标准品回退取更合理者
        projected = _project_concentration_on_quadratic(y_value, a, b, c, cmin, cmax)
        if projected > 0:
            return projected
        return fallback

    sqrt_d = float(np.sqrt(discriminant))
    roots = [(-b + sqrt_d) / (2 * a), (-b - sqrt_d) / (2 * a)]
    valid = [float(r) for r in roots if np.isfinite(r) and r >= 0]
    if not valid:
        projected = _project_concentration_on_quadratic(y_value, a, b, c, cmin, cmax)
        return projected if projected > 0 else fallback

    # 非单调时两个正根都可能成立：选更接近“标准品邻近估计”的那个
    target = fallback if fallback > 0 else (cmin + cmax) / 2.0
    in_range = [r for r in valid if cmin * 0.3 <= r <= cmax * 3.0]
    pool = in_range if in_range else valid
    return max(0.0, min(pool, key=lambda r: abs(r - target)))


def calculate_sample_concentrations_quadratic(sample_results, calibration_params):
    """反算样品浓度：优先等单调回归，其次二次反解/邻近估计。"""
    r2 = float(calibration_params.get("r_squared", 1.0))
    xs = np.asarray(calibration_params.get("X_original", []), dtype=float)
    ys = np.asarray(calibration_params.get("y_original", []), dtype=float)
    iso = calibration_params.get("isotonic_model")
    method_mode = str(calibration_params.get("quantification_method", "isotonic")).lower()
    use_isotonic = method_mode == "isotonic" and bool(calibration_params.get("use_isotonic")) and iso is not None

    prefer_interp = method_mode == "quadratic" and (r2 < 0.75)
    if xs.size >= 2 and ys.size == xs.size:
        y_sorted = ys[np.argsort(xs)]
        diffs = np.diff(y_sorted)
        monotonic = np.all(diffs >= -1e-9) or np.all(diffs <= 1e-9)
        prefer_interp = prefer_interp or (not monotonic)

    cmin = float(calibration_params.get("conc_min", 0.0))
    cmax = float(calibration_params.get("conc_max", 1.0))
    mid = (cmin + cmax) / 2.0

    for result in sample_results:
        y_value = _extract_y_value(result, calibration_params["y_axis_type"])
        interp = _interp_concentration_from_standards(
            y_value,
            calibration_params.get("X_original", []),
            calibration_params.get("y_original", []),
        )
        quad = solve_concentration_from_quadratic(y_value, calibration_params)

        if use_isotonic:
            try:
                conc = float(iso.predict([y_value])[0])
                method = "isotonic"
            except Exception:
                conc = interp
                method = "interp_fallback"
        elif method_mode == "quadratic":
            conc = quad if quad > 0 else interp
            method = "quadratic" if quad > 0 else "interp_fallback"
        elif prefer_interp:
            if cmin * 0.3 <= quad <= cmax * 3.0 and quad > 0:
                conc = quad if abs(quad - mid) <= abs(interp - mid) else interp
                method = "quadratic+interp"
            else:
                conc = interp
                method = "interp_fallback"
        else:
            conc = quad if quad > 0 else interp
            method = "quadratic" if quad > 0 else "interp_fallback"

        if conc <= 0 and xs.size:
            conc = interp if interp > 0 else float(max(cmin, 1e-12))
            method = "interp_fallback"

        conc = float(max(0.0, conc))
        range_info = assess_sample_quantification_range(y_value, conc, calibration_params)

        result["Calculated_Concentration"] = conc
        result["Concentration_Method"] = method
        result.update(range_info)

        if range_info["Out_of_Range"]:
            LOGGER.warning(
                f"Sample spot {result.get('Spot_Index', '?')} out of range: "
                f"y={y_value:.4g} (standards {range_info['Calibration_Y_Min']:.4g}"
                f"–{range_info['Calibration_Y_Max']:.4g}), "
                f"conc={conc:.6g} (validated {cmin:.6g}-{cmax:.6g}), "
                f"status={range_info['Range_Status']}"
            )
    return sample_results


def plot_calibration_curve_quadratic(standard_results, standard_concentrations, calibration_params, r_squared,
                                       save_path, background_type="other"):
    """
    绘制标准曲线：
    - 蓝点：实测响应（可能非单调）
    - 绿线：等单调平滑后的校准曲线（实际定量主要用它）
    - 红虚线：二次拟合（仅对照，可能呈 U 形）
    """
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial", "Helvetica", "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False

    y_axis_type = calibration_params["y_axis_type"]
    y_label = calibration_params["y_label"]
    concentrations = np.asarray(standard_concentrations, dtype=float)
    y_values = np.asarray([_extract_y_value(r, y_axis_type) for r in standard_results], dtype=float)
    y_mono = np.asarray(calibration_params.get("y_monotonic", y_values), dtype=float)
    if y_mono.shape != y_values.shape:
        y_mono = y_values
    bg_name = "Blue background" if background_type == "blue" else "Other background"
    spearman = calibration_params.get("spearman", None)
    use_isotonic = bool(calibration_params.get("use_isotonic"))
    quant_mode = str(calibration_params.get("quantification_method", "isotonic")).lower()

    order = np.argsort(concentrations)
    x_sorted = concentrations[order]
    y_sorted = y_values[order]
    y_mono_sorted = y_mono[order]

    plt.figure(figsize=(12, 8))
    plt.scatter(x_sorted, y_sorted, color="blue", s=70, label="Standards (measured, may be non-monotonic)", zorder=5)
    for x, y in zip(x_sorted, y_sorted):
        plt.annotate(f"{x:.5f}", (x, y), textcoords="offset points", xytext=(5, 5), ha="left", fontsize=8, alpha=0.7)

    x_dense = np.linspace(float(x_sorted.min()), float(x_sorted.max()), 200)
    y_dense = np.interp(x_dense, x_sorted, y_mono_sorted)
    if use_isotonic:
        mono_label = "Isotonic calibration (quantification)"
    else:
        mono_label = "Monotonic smooth curve (reference)"
    plt.plot(x_dense, y_dense, color="green", linewidth=2.5, label=mono_label, zorder=4)
    plt.scatter(x_sorted, y_mono_sorted, color="limegreen", s=40, marker="s", alpha=0.8, zorder=4)

    x_min, x_max = float(x_sorted.min()), float(x_sorted.max())
    x_fit = np.linspace(max(0.0, x_min * 0.8), x_max * 1.2, 200)
    y_fit = np.polyval(calibration_params["coefs"], x_fit)
    quad_r2 = float(calibration_params.get("r_squared", r_squared))
    if use_isotonic:
        quad_label = f"Quadratic fit (reference, R2={quad_r2:.3f})"
        quad_style = ("r--", 1.5, 0.7)
    else:
        quad_label = f"Quadratic calibration (quantification, R2={quad_r2:.3f})"
        quad_style = ("r-", 2.5, 1.0)
    plt.plot(x_fit, y_fit, quad_style[0], linewidth=quad_style[1], alpha=quad_style[2], label=quad_label)

    plt.xlabel("Concentration", fontsize=12)
    plt.ylabel(y_label, fontsize=12)
    title = f"TLC calibration curve ({bg_name})\nConcentration vs {y_label}"
    if spearman is not None:
        if use_isotonic:
            title += f"\nMeasured Spearman={float(spearman):.3f} (green = isotonic quantification)"
        else:
            title += f"\nMeasured Spearman={float(spearman):.3f} (red = quadratic quantification)"
    plt.title(title, fontsize=13)
    plt.legend(fontsize=9, loc="best")
    plt.grid(True, alpha=0.3)

    a, b, c = calibration_params["a"], calibration_params["b"], calibration_params["c"]
    info = f"Quadratic: y={a:.4g}x^2+{b:.4g}x+{c:.4g} (R2={quad_r2:.4f})"
    if use_isotonic:
        info += f"\nMethod: isotonic regression (iso R2={float(calibration_params.get('r_squared_isotonic', 0)):.3f})"
    else:
        info += "\nMethod: quadratic back-calculation (paper reproduction mode)"
    plt.text(
        0.02, 0.98, info, transform=plt.gca().transAxes, fontsize=10,
        verticalalignment="top",
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.85),
    )

    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close()


def calculate_local_background(gray_im, box, margin=10):
    """计算斑点周围的局部背景（单斑点回退用；优先改用泳道共用背景）。"""
    height, width = gray_im.shape

    x1 = max(0, box[0] - margin)
    y1 = max(0, box[1] - margin)
    x2 = min(width, box[2] + margin)
    y2 = min(height, box[3] + margin)

    background_mask = np.ones((y2 - y1, x2 - x1), dtype=bool)
    spot_x1 = box[0] - x1
    spot_y1 = box[1] - y1
    spot_x2 = box[2] - x1
    spot_y2 = box[3] - y1

    if (0 <= spot_x1 < (x2 - x1) and 0 <= spot_y1 < (y2 - y1) and
            0 <= spot_x2 <= (x2 - x1) and 0 <= spot_y2 <= (y2 - y1)):
        background_mask[spot_y1:spot_y2, spot_x1:spot_x2] = False

    background_region = gray_im[y1:y2, x1:x2]
    if np.any(background_mask):
        # 用中位数，降低邻近斑点亮/暗边缘污染
        local_bg = float(np.median(background_region[background_mask]))
    else:
        local_bg = float(np.median(gray_im))

    return local_bg


def estimate_lane_background(gray_im, spot_boxes, y_pad: int = 45, x_pad: int = 10) -> float:
    """
    估计整条展开泳道的共用背景。
    在斑点所在水平带内，排除所有斑点 x 范围后取中位数，避免“局部环状背景”
    被左右邻近斑点污染，从而破坏标准品单调性。
    """
    if gray_im is None or gray_im.size == 0:
        return 1.0
    h, w = gray_im.shape[:2]
    if not spot_boxes:
        return float(np.median(gray_im))

    y_centers = [((int(b[1]) + int(b[3])) // 2) for b in spot_boxes]
    y_med = int(np.median(y_centers))
    y1 = max(0, y_med - y_pad)
    y2 = min(h, y_med + y_pad)
    band = gray_im[y1:y2, :].astype(np.float32)
    keep = np.ones(band.shape, dtype=bool)
    for box in spot_boxes:
        xx1 = max(0, int(box[0]) - x_pad)
        xx2 = min(w, int(box[2]) + x_pad)
        if xx2 > xx1:
            keep[:, xx1:xx2] = False

    vals = band[keep]
    if vals.size < 80:
        # 回退：图像四边
        m = max(6, min(h, w) // 20)
        border = np.concatenate([
            gray_im[:m, :].ravel(),
            gray_im[-m:, :].ravel(),
            gray_im[:, :m].ravel(),
            gray_im[:, -m:].ravel(),
        ]).astype(np.float32)
        return float(np.median(border)) if border.size else float(np.median(gray_im))
    return float(np.median(vals))


def detect_signal_polarity(spot_means, background: float) -> str:
    """荧光：斑点比背景亮；吸收：斑点比背景暗。"""
    if not spot_means:
        return "fluorescence"
    brighter = sum(1 for m in spot_means if float(m) >= float(background))
    return "fluorescence" if brighter >= 0.5 * len(spot_means) else "absorption"


def compute_net_integral(gray_roi, background: float, mask_roi=None, polarity: str = "auto"):
    """
    极性感知净信号积分：
    - fluorescence: sum(max(I - bg, 0))
    - absorption:   sum(max(bg - I, 0))
    有 mask 时只统计斑点像素，避免固定矩形里大量底板干扰单调性。
    """
    if gray_roi is None or gray_roi.size == 0:
        return 0.0, 0.0, polarity if polarity != "auto" else "fluorescence"

    roi = gray_roi.astype(np.float32)
    if mask_roi is not None:
        mask_bin = mask_roi > 0.5
        pixels = roi[mask_bin] if np.any(mask_bin) else roi.ravel()
    else:
        pixels = roi.ravel()

    if pixels.size == 0:
        return 0.0, 0.0, polarity if polarity != "auto" else "fluorescence"

    mean_fg = float(pixels.mean())
    if polarity == "auto":
        polarity = "fluorescence" if mean_fg >= float(background) else "absorption"

    bg = float(background)
    if polarity == "fluorescence":
        net = np.maximum(pixels - bg, 0.0)
    else:
        net = np.maximum(bg - pixels, 0.0)

    return float(net.sum()), float(net.mean()), polarity


def compute_masked_od(gray_roi, background: float, mask_roi=None) -> tuple[float, float]:
    """仅在 mask（或整块 ROI）上累计光密度，避免矩形底板虚高。"""
    if gray_roi is None or gray_roi.size == 0 or background <= 0:
        return 0.0, 0.0
    od_map = calculate_optical_density(gray_roi, background)
    if mask_roi is not None:
        mask_bin = mask_roi > 0.5
        if np.any(mask_bin):
            vals = od_map[mask_bin]
        else:
            vals = od_map.ravel()
    else:
        vals = od_map.ravel()
    if vals.size == 0:
        return 0.0, 0.0
    return float(vals.sum()), float(vals.mean())


def extract_lane_chromatogram(
    gray_im: np.ndarray,
    y_center: int,
    half_height: int,
    polarity: str,
    lane_bg: float,
) -> tuple[np.ndarray, np.ndarray]:
    """
    沿展开方向提取一维色谱图：每个 x 取竖直窄带平均灰度，再转成净信号。
    荧光: max(I-bg,0)；吸收: max(bg-I,0)。
    """
    h, w = gray_im.shape[:2]
    y1 = max(0, int(y_center) - int(half_height))
    y2 = min(h, int(y_center) + int(half_height) + 1)
    if y2 <= y1 or w <= 0:
        return np.arange(0), np.zeros(0, dtype=np.float32)

    band = gray_im[y1:y2, :].astype(np.float32)
    col_mean = band.mean(axis=0)
    bg = float(lane_bg)
    if polarity == "fluorescence":
        net = np.maximum(col_mean - bg, 0.0)
    else:
        net = np.maximum(bg - col_mean, 0.0)
    return np.arange(w, dtype=np.float32), net.astype(np.float32)


def integrate_1d_peak_areas(
    profile: np.ndarray,
    x_centers: list[int],
    default_half_width: int = 65,
) -> list[float]:
    """
    在相邻斑点中点处分窗，窗内扣线性基线后梯形积分，得到一维峰面积。
    """
    if profile is None or len(profile) == 0 or not x_centers:
        return [0.0] * len(x_centers)

    w = len(profile)
    xs = [int(np.clip(x, 0, w - 1)) for x in x_centers]
    n = len(xs)
    areas: list[float] = []

    for i, xc in enumerate(xs):
        if n == 1:
            left = max(0, xc - default_half_width)
            right = min(w - 1, xc + default_half_width)
        else:
            if i == 0:
                left = max(0, xc - default_half_width)
                right = (xc + xs[i + 1]) // 2
            elif i == n - 1:
                left = (xs[i - 1] + xc) // 2
                right = min(w - 1, xc + default_half_width)
            else:
                left = (xs[i - 1] + xc) // 2
                right = (xc + xs[i + 1]) // 2
            # 防止窗过窄
            left = min(left, xc)
            right = max(right, xc)

        if right <= left:
            areas.append(0.0)
            continue

        seg = profile[left: right + 1].astype(np.float64)
        # 线性基线：连接窗口两端
        baseline = np.linspace(float(seg[0]), float(seg[-1]), seg.size)
        net = np.maximum(seg - baseline, 0.0)
        try:
            areas.append(float(np.trapezoid(net)))
        except AttributeError:
            areas.append(float(np.trapz(net)))

    return areas


def attach_1d_peak_areas(
    results: list[dict],
    gray_im: np.ndarray,
    band_half_height: int,
    polarity: str,
    lane_bg: float,
    default_half_width: int = 65,
    profile_save_path=None,
) -> list[dict]:
    """给每个斑点写入 Peak_Area_1D，可选保存色谱图。"""
    if not results or gray_im is None or gray_im.size == 0:
        return results

    y_center = int(np.median([r["Y_Position"] for r in results]))
    x_centers = [int(r["X_Position"]) for r in results]
    xs, profile = extract_lane_chromatogram(gray_im, y_center, band_half_height, polarity, lane_bg)
    areas = integrate_1d_peak_areas(profile, x_centers, default_half_width=default_half_width)

    for r, a in zip(results, areas):
        r["Peak_Area_1D"] = round(float(a), 2)

    print(f"1D peak areas: {areas}")

    if profile_save_path is not None and xs.size > 0:
        try:
            plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial", "Helvetica", "sans-serif"]
            plt.rcParams["axes.unicode_minus"] = False
            plt.figure(figsize=(12, 4))
            plt.plot(xs, profile, color="steelblue", linewidth=1.2, label="1D net-signal profile")
            for r, a in zip(results, areas):
                plt.axvline(r["X_Position"], color="orange", alpha=0.35, linewidth=1)
                plt.text(r["X_Position"], max(profile) * 0.95 if profile.max() > 0 else 1.0,
                         f"#{r['Spot_Index']}\n{a:.0f}", ha="center", va="top", fontsize=7)
            plt.xlabel("Development direction X (pixel)")
            plt.ylabel("Net signal")
            plt.title(f"1D peak profile ({polarity}, bg={lane_bg:.1f})")
            plt.legend(loc="upper right", fontsize=8)
            plt.tight_layout()
            plt.savefig(profile_save_path, dpi=200, bbox_inches="tight")
            plt.close()
        except Exception as e:
            print(f"Failed to save 1D profile plot: {e}")

    return results


def calculate_peak_area(gray_im, mask, box, baseline_method='local', baseline_value=None):
    """
    计算斑点的峰面积积分（替代AUC）

    参数:
    - gray_im: 灰度图像
    - mask: 斑点的二值掩码
    - box: 边界框坐标
    - baseline_method: 基线计算方法 ('local', 'global', 'min', 'fixed')
    - baseline_value: 固定基线值

    返回:
    - peak_area: 峰面积积分
    - baseline: 使用的基线值
    - intensity_data: 强度数据
    """
    x1, y1, x2, y2 = box

    # 提取斑点区域
    spot_region = gray_im[y1:y2, x1:x2]
    spot_mask = mask[y1:y2, x1:x2]

    if spot_region.size == 0:
        return 0, 0, None

    # 确定基线
    if baseline_method == 'local':
        # 使用斑点周围的局部背景
        local_bg = calculate_local_background(gray_im, box)
        baseline = local_bg
    elif baseline_method == 'global':
        baseline = gray_im.mean()
    elif baseline_method == 'min':
        baseline = np.min(spot_region[spot_mask]) if np.any(spot_mask) else np.min(spot_region)
    elif baseline_method == 'fixed' and baseline_value is not None:
        baseline = baseline_value
    else:
        baseline = np.mean(spot_region)  # 默认使用斑点区域平均值

    # 计算峰面积积分 - 使用二维积分方法
    if np.any(spot_mask):
        # 仅对掩码区域计算
        spot_intensities = spot_region[spot_mask]
    else:
        # 如果没有有效掩码，使用整个区域
        spot_intensities = spot_region.flatten()

    # 减去基线并确保非负
    above_baseline = np.maximum(spot_intensities - baseline, 0)

    # 计算峰面积积分（所有像素的强度之和）
    peak_area = np.sum(above_baseline)

    return peak_area, baseline, spot_intensities


def calculate_calibration_curve_enhanced(standard_results, standard_concentrations, y_axis_type='sum_od',
                                         transform_type='none'):
    """
    增强的标准曲线计算，支持多种数据变换

    参数:
    - standard_results: 标准品斑点的结果列表
    - standard_concentrations: 标准品浓度列表
    - y_axis_type: 纵坐标类型 ('sum_gray', 'mean_gray', 'sum_od', 'mean_od')
    - transform_type: 数据变换类型 ('none', 'log', 'sqrt', 'reciprocal', 'log_log', 'power')

    返回:
    - calibration_params: 校准曲线参数
    - r_squared: 决定系数
    """
    if len(standard_results) != len(standard_concentrations):
        raise ValueError("Standard count does not match concentration list length")

    # 根据选择的纵坐标类型提取数据
    if y_axis_type == 'sum_gray':
        y_values = [result["Sum_Gray"] for result in standard_results]
        y_label = "Total gray"
    elif y_axis_type == 'mean_gray':
        y_values = [result["Mean_Gray"] for result in standard_results]
        y_label = "Mean gray"
    elif y_axis_type == 'sum_od':
        y_values = [result["Sum_OD"] for result in standard_results]
        y_label = "Total OD"
    elif y_axis_type == 'mean_od':
        y_values = [result["Mean_OD"] for result in standard_results]
        y_label = "Mean OD"
    else:
        raise ValueError("Unsupported y_axis_type")

    concentrations = standard_concentrations

    # 数据变换
    X_orig = np.array(concentrations).reshape(-1, 1)
    y_orig = np.array(y_values)

    # 应用数据变换
    if transform_type == 'log':
        # 对数变换
        X = np.log10(X_orig + 1e-10)  # 避免log(0)
        y = y_orig
        x_label = "log(Concentration)"
    elif transform_type == 'sqrt':
        # 平方根变换
        X = np.sqrt(X_orig)
        y = y_orig
        x_label = "sqrt(Concentration)"
    elif transform_type == 'reciprocal':
        # 倒数变换
        X = 1.0 / (X_orig + 1e-10)  # 避免除零
        y = y_orig
        x_label = "1/Concentration"
    elif transform_type == 'log_log':
        # 双对数变换
        X = np.log10(X_orig + 1e-10)
        y = np.log10(y_orig + 1e-10)
        x_label = "log(Concentration)"
        y_label = f"log({y_label})"
    elif transform_type == 'power':
        # 幂变换 (使用Box-Cox变换的简化版本)
        X = X_orig
        y = np.sqrt(y_orig)  # 使用平方根变换
        y_label = f"√{y_label}"
        x_label = "Concentration"
    else:
        # 无变换
        X = X_orig
        y = y_orig
        x_label = "Concentration"

    # 线性回归
    model = LinearRegression()
    model.fit(X, y)

    # 计算R²
    y_pred = model.predict(X)
    r_squared = r2_score(y, y_pred)

    calibration_params = {
        'slope': model.coef_[0],
        'intercept': model.intercept_,
        'model': model,
        'y_axis_type': y_axis_type,
        'y_label': y_label,
        'x_label': x_label,
        'transform_type': transform_type,
        'X_original': X_orig.flatten(),
        'y_original': y_orig
    }

    return calibration_params, r_squared


def calculate_sample_concentrations_enhanced(sample_results, calibration_params):
    """
    计算样品浓度 - 支持高精度和多种数据变换

    参数:
    - sample_results: 样品斑点的结果列表
    - calibration_params: 校准曲线参数

    返回:
    - 包含浓度信息的样品结果列表
    """
    slope = calibration_params['slope']
    intercept = calibration_params['intercept']
    model = calibration_params['model']
    y_axis_type = calibration_params['y_axis_type']
    transform_type = calibration_params['transform_type']

    for result in sample_results:
        # 根据校准曲线使用的纵坐标类型选择相应的值
        if y_axis_type == 'sum_gray':
            y_value = result["Sum_Gray"]
        elif y_axis_type == 'mean_gray':
            y_value = result["Mean_Gray"]
        elif y_axis_type == 'sum_od':
            y_value = result["Sum_OD"]
        elif y_axis_type == 'mean_od':
            y_value = result["Mean_OD"]
        else:
            y_value = result["Sum_Gray"]  # 默认使用总灰度值

        # 根据变换类型计算浓度
        if transform_type == 'log':
            # 对数变换的反函数
            if slope != 0:
                log_concentration = (y_value - intercept) / slope
                concentration = 10 ** log_concentration
            else:
                concentration = 0
        elif transform_type == 'sqrt':
            # 平方根变换的反函数
            if slope != 0:
                sqrt_concentration = (y_value - intercept) / slope
                concentration = sqrt_concentration ** 2
            else:
                concentration = 0
        elif transform_type == 'reciprocal':
            # 倒数变换的反函数
            if slope != 0 and y_value != intercept:
                reciprocal_concentration = (y_value - intercept) / slope
                if reciprocal_concentration != 0:
                    concentration = 1.0 / reciprocal_concentration
                else:
                    concentration = 0
            else:
                concentration = 0
        elif transform_type == 'log_log':
            # 双对数变换的反函数
            if slope != 0:
                log_y = np.log10(y_value + 1e-10)
                log_concentration = (log_y - intercept) / slope
                concentration = 10 ** log_concentration
            else:
                concentration = 0
        elif transform_type == 'power':
            # 幂变换的反函数
            if slope != 0:
                sqrt_y = np.sqrt(y_value)
                concentration = (sqrt_y - intercept) / slope
                concentration = concentration ** 2  # 因为我们用了平方根变换
            else:
                concentration = 0
        else:
            # 无变换
            if slope != 0:
                concentration = (y_value - intercept) / slope
            else:
                concentration = 0

        # 确保浓度不为负
        concentration = max(0, concentration)

        result["Calculated_Concentration"] = concentration

    return sample_results


def plot_calibration_curve_enhanced(standard_results, standard_concentrations, calibration_params, r_squared,
                                    save_path):
    """
    绘制增强的标准曲线图 - 支持多种数据变换和高精度显示
    """
    y_axis_type = calibration_params['y_axis_type']
    y_label = calibration_params['y_label']
    x_label = calibration_params['x_label']
    transform_type = calibration_params['transform_type']

    # 根据选择的纵坐标类型提取数据
    if y_axis_type == 'sum_gray':
        y_values = [result["Sum_Gray"] for result in standard_results]
    elif y_axis_type == 'mean_gray':
        y_values = [result["Mean_Gray"] for result in standard_results]
    elif y_axis_type == 'sum_od':
        y_values = [result["Sum_OD"] for result in standard_results]
    elif y_axis_type == 'mean_od':
        y_values = [result["Mean_OD"] for result in standard_results]

    concentrations = standard_concentrations

    plt.figure(figsize=(12, 8))

    # 散点图
    plt.scatter(concentrations, y_values, color='blue', s=60, label='Standard points', zorder=5)

    # 在点上标注精确的浓度值
    for i, (x, y) in enumerate(zip(concentrations, y_values)):
        plt.annotate(f'{x:.5f}', (x, y), textcoords="offset points",
                     xytext=(5, 5), ha='left', fontsize=8, alpha=0.7)

    # 回归线
    x_min, x_max = min(concentrations), max(concentrations)
    x_fit = np.linspace(x_min, x_max, 100)

    # 根据变换类型生成拟合线
    if transform_type == 'log':
        x_fit_transformed = np.log10(x_fit + 1e-10)
        y_fit = calibration_params['slope'] * x_fit_transformed + calibration_params['intercept']
    elif transform_type == 'sqrt':
        x_fit_transformed = np.sqrt(x_fit)
        y_fit = calibration_params['slope'] * x_fit_transformed + calibration_params['intercept']
    elif transform_type == 'reciprocal':
        x_fit_transformed = 1.0 / (x_fit + 1e-10)
        y_fit = calibration_params['slope'] * x_fit_transformed + calibration_params['intercept']
    elif transform_type == 'log_log':
        x_fit_transformed = np.log10(x_fit + 1e-10)
        y_fit_log = calibration_params['slope'] * x_fit_transformed + calibration_params['intercept']
        y_fit = 10 ** y_fit_log
    elif transform_type == 'power':
        y_fit_sqrt = calibration_params['slope'] * x_fit + calibration_params['intercept']
        y_fit = y_fit_sqrt ** 2
    else:
        y_fit = calibration_params['slope'] * x_fit + calibration_params['intercept']

    plt.plot(x_fit, y_fit, 'r-', linewidth=2, label=f'Calibration curve (R2 = {r_squared:.6f})')

    plt.xlabel(x_label, fontsize=12)
    plt.ylabel(y_label, fontsize=12)
    plt.title(f'TLC calibration - {x_label} vs {y_label}\nTransform: {transform_type}', fontsize=14)
    plt.legend(fontsize=10)
    plt.grid(True, alpha=0.3)

    # 添加回归方程和统计信息
    equation = f'y = {calibration_params["slope"]:.6f}x + {calibration_params["intercept"]:.6f}'
    plt.text(0.05, 0.95, equation, transform=plt.gca().transAxes, fontsize=11,
             verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

    plt.text(0.05, 0.85, f'R² = {r_squared:.6f}', transform=plt.gca().transAxes, fontsize=11,
             verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))

    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close()


def find_best_transform(standard_results, standard_concentrations, y_axis_type='sum_od'):
    """
    自动寻找最佳的数据变换方法

    返回:
    - best_transform: 最佳变换方法
    - best_r_squared: 最佳R²值
    - all_results: 所有变换方法的结果
    """
    transform_methods = ['none', 'log', 'sqrt', 'reciprocal', 'log_log', 'power']
    best_r_squared = -1
    best_transform = 'none'
    all_results = {}

    for transform in transform_methods:
        try:
            calibration_params, r_squared = calculate_calibration_curve_enhanced(
                standard_results, standard_concentrations, y_axis_type, transform
            )
            all_results[transform] = {
                'r_squared': r_squared,
                'slope': calibration_params['slope'],
                'intercept': calibration_params['intercept']
            }

            if r_squared > best_r_squared:
                best_r_squared = r_squared
                best_transform = transform
        except Exception as e:
            print(f"Transform {transform} failed: {e}")
            continue

    return best_transform, best_r_squared, all_results


def process_spots_sorted(det, masks, gray_im, color_im, fixed_width, fixed_height, y_tolerance=60):
    """增强的斑点处理函数，包含详细的光密度计算和调试信息"""
    boxes = det[:, :4].cpu().numpy().astype(int)
    masks = masks.cpu().numpy()

    # 1. 找到基准线
    y_centers = [(box[1] + box[3]) // 2 for box in boxes]
    y_line = np.median(y_centers)

    # 2. 收集同一行的斑点
    spots_in_line = []
    for idx, (box, mask) in enumerate(zip(boxes, masks)):
        y_center = (box[1] + box[3]) // 2
        if abs(y_center - y_line) <= y_tolerance:
            spots_in_line.append({
                'index': idx,
                'box': box,
                'mask': mask,
                'x_center': (box[0] + box[2]) // 2,
                'y_center': y_center
            })

    # 3. 按x坐标排序（左→右 = 标准品浓度顺序）
    spots_in_line.sort(key=lambda x: x['x_center'])

    results = []
    global_mean_bg = float(np.median(gray_im)) if gray_im.size else 1.0
    height, width = gray_im.shape

    # 先准备固定 ROI，再估共用泳道背景与信号极性
    prepared = []
    for spot in spots_in_line:
        center_x = spot['x_center']
        center_y = spot['y_center']
        start_x = max(0, center_x - fixed_width // 2)
        start_y = max(0, center_y - fixed_height // 2)
        end_x = min(width, start_x + fixed_width)
        end_y = min(height, start_y + fixed_height)
        actual_width = end_x - start_x
        actual_height = end_y - start_y
        if actual_width < fixed_width * 0.8 or actual_height < fixed_height * 0.8:
            continue
        fixed_roi = gray_im[start_y:end_y, start_x:end_x]
        if fixed_roi.size == 0:
            continue
        full_mask = spot["mask"]
        if full_mask.ndim > 2:
            full_mask = np.squeeze(full_mask)
        mask_roi = full_mask[start_y:end_y, start_x:end_x]
        roi_box = [start_x, start_y, end_x, end_y]
        prepared.append({
            "spot": spot,
            "roi_box": roi_box,
            "fixed_roi": fixed_roi,
            "color_roi": color_im[start_y:end_y, start_x:end_x],
            "mask_roi": mask_roi,
            "center_x": center_x,
            "center_y": center_y,
            "actual_width": actual_width,
            "actual_height": actual_height,
            "mean_fg": float(fixed_roi.mean()),
        })

    lane_boxes = [p["roi_box"] for p in prepared]
    lane_bg = estimate_lane_background(gray_im, lane_boxes)
    polarity = detect_signal_polarity([p["mean_fg"] for p in prepared], lane_bg)

    print(f"Global background (median): {global_mean_bg:.2f}")
    print(f"Lane shared background: {lane_bg:.2f}")
    print(f"Signal polarity: {polarity} ({'fluorescence = spot brighter' if polarity == 'fluorescence' else 'absorption = spot darker'})")
    if global_mean_bg < 10:
        print("Warning: low global background may affect OD calculation")

    for spot_idx, item in enumerate(prepared):
        spot = item["spot"]
        box = spot["box"]
        mask = spot["mask"]
        fixed_roi = item["fixed_roi"]
        color_roi = item["color_roi"]
        mask_roi = item["mask_roi"]
        center_x = item["center_x"]
        center_y = item["center_y"]
        actual_width = item["actual_width"]
        actual_height = item["actual_height"]
        mean_fg = item["mean_fg"]
        sum_gray = int(fixed_roi.sum())

        local_bg = calculate_local_background(gray_im, item["roi_box"], margin=15)
        # 定量统一用泳道共用背景，避免邻近斑点污染导致非单调
        bg_use = lane_bg

        sum_gray_corrected, mean_gray_corrected, _ = compute_net_integral(
            fixed_roi, bg_use, mask_roi, polarity=polarity
        )
        net_signal = sum_gray_corrected

        sum_od, mean_od = compute_masked_od(fixed_roi, bg_use, mask_roi)
        sum_od_global, mean_od_global = compute_masked_od(fixed_roi, global_mean_bg, mask_roi)
        sum_od_local, mean_od_local = compute_masked_od(fixed_roi, local_bg, mask_roi)
        od_method = "lane_shared+mask"

        roi_clipped = (actual_width < fixed_width) or (actual_height < fixed_height)
        if roi_clipped:
            print(
                f"Warning: spot {spot_idx} near image edge; ROI clipped to {actual_width}x{actual_height}; "
                f"integral may be biased (raw gray sum={sum_gray}, net signal={net_signal:.0f})"
            )

        print(f"\n--- Spot {spot_idx} OD / net signal ---")
        print(f"ROI shape: {fixed_roi.shape}, mean intensity: {mean_fg:.2f}")
        print(f"Local bg: {local_bg:.2f}, lane bg: {bg_use:.2f}, global: {global_mean_bg:.2f}")
        print(f"Net signal: {net_signal:.2f}, total OD in mask: {sum_od:.4f}")

        peak_area, baseline_peak, intensity_data = calculate_peak_area(gray_im, mask, box, 'local')

        if color_roi.size > 0:
            avg_B = np.mean(color_roi[:, :, 0])
            avg_G = np.mean(color_roi[:, :, 1])
            avg_R = np.mean(color_roi[:, :, 2])
            hsv_roi = cv2.cvtColor(color_roi, cv2.COLOR_BGR2HSV)
            avg_H = np.mean(hsv_roi[:, :, 0])
            avg_S = np.mean(hsv_roi[:, :, 1])
            avg_V = np.mean(hsv_roi[:, :, 2])
            lab_roi = cv2.cvtColor(color_roi, cv2.COLOR_BGR2Lab)
            avg_L = np.mean(lab_roi[:, :, 0])
            avg_A = np.mean(lab_roi[:, :, 1])
            avg_B_lab = np.mean(lab_roi[:, :, 2])
            C_map = np.sqrt(lab_roi[:, :, 1].astype(float) ** 2 + lab_roi[:, :, 2].astype(float) ** 2)
            avg_C = np.mean(C_map)
        else:
            avg_R = avg_G = avg_B = 0
            avg_H = avg_S = avg_V = 0
            avg_L = avg_A = avg_B_lab = avg_C = 0

        ratio_local = mean_fg / local_bg if local_bg > 0 else 0
        ratio_global = mean_fg / global_mean_bg if global_mean_bg > 0 else 0
        ratio_lane = mean_fg / bg_use if bg_use > 0 else 0

        result = {
            "Image": "",
            "Spot_Index": spot_idx,
            "Original_Index": spot['index'],
            "X_Position": center_x,
            "Y_Position": center_y,
            "Width": actual_width,
            "Height": actual_height,
            "Area": actual_width * actual_height,
            "Mean_Gray": round(float(mean_fg), 2),
            "Sum_Gray": sum_gray,
            "Sum_Gray_Corrected": round(float(sum_gray_corrected), 2),
            "Mean_Gray_Corrected": round(float(mean_gray_corrected), 2),
            "Net_Signal": round(float(net_signal), 2),
            "Signal_Polarity": polarity,
            "Lane_Background": round(float(bg_use), 2),
            "ROI_Clipped": roi_clipped,
            "Mean_OD": round(float(mean_od), 4),
            "Sum_OD": round(float(sum_od), 4),
            "Mean_OD_Global": round(float(mean_od_global), 4),
            "Sum_OD_Global": round(float(sum_od_global), 4),
            "Mean_OD_Local": round(float(mean_od_local), 4),
            "Sum_OD_Local": round(float(sum_od_local), 4),
            "OD_Method": od_method,
            "IOD": round(float(sum_od_global), 4),
            "Peak_Area": round(float(peak_area), 4),
            "Baseline_Peak": round(float(bg_use), 2),
            "Global_Background": round(float(global_mean_bg), 2),
            "Local_Background": round(float(local_bg), 2),
            "Gray_Ratio_Global": round(float(ratio_global), 4),
            "Gray_Ratio_Local": round(float(ratio_local), 4),
            "Gray_Ratio_Lane": round(float(ratio_lane), 4),
            "Center_Point": f"{center_x},{center_y}",
            "R": round(float(avg_R), 2),
            "G": round(float(avg_G), 2),
            "B": round(float(avg_B), 2),
            "H": round(float(avg_H), 2),
            "S": round(float(avg_S), 2),
            "V": round(float(avg_V), 2),
            "L": round(float(avg_L), 2),
            "A": round(float(avg_A), 2),
            "B_lab": round(float(avg_B_lab), 2),
            "C": round(float(avg_C), 2),
            "Spot_Type": "",
            "Known_Concentration": None,
            "Calculated_Concentration": None,
            "Out_of_Range": False,
            "Range_Status": "",
            "Response_In_Range": True,
            "Concentration_In_Range": True,
            "Spot_Source": "auto",
            "Manual_Rect": "",
        }
        results.append(result)
        print(
            f"Spot {spot_idx} final - raw gray sum: {sum_gray}, "
            f"net signal: {net_signal:.0f}, total OD in mask: {sum_od:.4f}"
        )

    return results


@smart_inference_mode()
def run(
        weights=ROOT / "yolov5s-seg.pt",  # model.pt path(s)
        source=ROOT / "data/images",  # file/dir/URL/glob/screen/0(webcam)
        data=ROOT / "data/coco128.yaml",  # dataset.yaml path
        imgsz=(640, 640),  # inference size (height, width)
        conf_thres=0.15,  # confidence threshold (lower = more sensitive to detect weak spots)
        iou_thres=0.3,  # NMS IOU threshold
        max_det=1000,  # maximum detections per image
        device="",  # cuda device, i.e. 0 or 0,1,2,3 or cpu
        view_img=False,  # show results
        save_txt=False,  # save results to *.txt
        save_conf=False,  # save confidences in --save-txt labels
        save_crop=False,  # save cropped prediction boxes
        nosave=False,  # do not save images/videos
        classes=None,  # filter by class: --class 0, or --class 0 2 3
        agnostic_nms=False,  # class-agnostic NMS
        augment=False,  # augmented inference
        visualize=False,  # visualize features
        update=False,  # update all models
        project=ROOT / "runs/predict-seg",  # save results to project/name
        name="exp",  # save results to project/name
        exist_ok=False,  # existing project/name ok, do not increment
        line_thickness=3,  # bounding box thickness (pixels)
        hide_labels=False,  # hide labels
        hide_conf=False,  # hide confidences
        half=False,  # use FP16 half-precision inference
        dnn=False,  # use OpenCV DNN for ONNX inference
        vid_stride=1,  # video frame-rate stride
        retina_masks=False,
        fixed_width=30,  # 矩形宽度
        fixed_height=20,  # 矩形高度
        standard_num=5,  # 新增：标准品数量
        standard_concentrations="0.125,0.25,0.5,1,2",  # 新增：标准品浓度
        y_axis_type='sum_od',  # 修改：默认使用总光密度值
        transform_type='auto',  # 新增：数据变换类型
        mask_interference=True,  # 新增：是否遮盖水平线外干扰斑点后二次推理（默认启用）
        mask_color='background',  # 新增：遮盖颜色 background/white/black
        mask_pad=6,  # 新增：遮盖框膨胀像素
        mask_save=True,  # 新增：保存遮盖后的中间图（默认启用）
        mask_x_margin=30,  # 新增：自动保护右侧条带的x边界外扩像素
        y_tolerance=60,  # 新增：水平带容忍范围（像素），用于判断斑点是否在同一水平线
        manual_mark=True,  # 新增：启用手动矩形补标
        manual_save_json=True,  # 新增：保存手动框选json
        concentrations_by_image=None,  # 新增：按图片名读取浓度（由 run_analysis.py 传入）
        quantification_method="isotonic",  # isotonic=等单调回归(默认); quadratic=二次反算(论文复现)
        imaging_mode="auto",  # auto/366nm/visible/254nm，固定 IGI 或 IOD
):
    """Run YOLOv5 segmentation inference on diverse sources including images, videos, directories, and streams."""
    try:
        from utils.load_user_config import normalize_quantification_method, normalize_imaging_mode
        quantification_method = normalize_quantification_method(quantification_method)
        imaging_mode = normalize_imaging_mode(imaging_mode)
    except Exception:
        quantification_method = str(quantification_method or "isotonic").strip().lower()
        if quantification_method not in ("isotonic", "quadratic"):
            quantification_method = "isotonic"
        imaging_mode = str(imaging_mode or "auto").strip().lower()

    source = str(source)
    save_img = not nosave and not source.endswith(".txt")  # save inference images
    is_file = Path(source).suffix[1:] in (IMG_FORMATS + VID_FORMATS)
    is_url = source.lower().startswith(("rtsp://", "rtmp://", "http://", "https://"))
    webcam = source.isnumeric() or source.endswith(".streams") or (is_url and not is_file)
    screenshot = source.lower().startswith("screen")
    if is_url and is_file:
        source = check_file(source)  # download

    # 解析标准品浓度 - 支持高精度小数
    if concentrations_by_image is None:
        try:
            from utils.load_user_config import load_concentrations
            concentrations_by_image = load_concentrations()
            LOGGER.info("Loaded concentrations from user_input/standard_concentrations.csv")
        except Exception as e:
            LOGGER.warning(f"Failed to load concentration table: {e}")
            concentrations_by_image = None

    try:
        standard_conc = [float(x.strip()) for x in standard_concentrations.split(",")]
        if len(standard_conc) != standard_num:
            LOGGER.warning(
                f"Concentration count ({len(standard_conc)}) != standard_num ({standard_num}); using first {min(len(standard_conc), standard_num)} values")
            standard_conc = standard_conc[:standard_num]

        # 验证浓度精度
        for i, conc in enumerate(standard_conc):
            if abs(conc - round(conc, 10)) > 1e-10:  # 检查是否支持高精度
                LOGGER.info(f"Standard {i + 1}: concentration = {conc:.10f}")
    except Exception as e:
        LOGGER.error(f"Failed to parse standard concentrations: {e}")
        standard_conc = [0.1 * (i + 1) for i in range(standard_num)]  # 默认浓度

    # Directories
    save_dir = increment_path(Path(project) / name, exist_ok=exist_ok)  # increment run
    (save_dir / "labels" if save_txt else save_dir).mkdir(parents=True, exist_ok=True)  # make dir
    # 保存本次运行的完整参数，方便复现/对比不同 exp 目录的差异
    try:
        yaml_save(save_dir / "opt.yaml", {k: (str(v) if isinstance(v, Path) else v) for k, v in locals().items()
                                          if k in {
                                              "weights", "source", "data", "imgsz", "conf_thres", "iou_thres", "max_det",
                                              "device", "view_img", "save_txt", "save_conf", "save_crop", "nosave",
                                              "classes", "agnostic_nms", "augment", "visualize", "update", "project",
                                              "name", "exist_ok", "line_thickness", "hide_labels", "hide_conf", "half",
                                              "dnn", "vid_stride", "retina_masks", "fixed_width", "fixed_height",
                                              "standard_num", "standard_concentrations", "y_axis_type", "transform_type",
                                              "quantification_method", "imaging_mode",
                                              "mask_interference", "mask_color", "mask_pad", "mask_save", "mask_x_margin",
                                              "y_tolerance",
                                              "manual_mark", "manual_save_json",
                                          }})
    except Exception as e:
        LOGGER.warning(f"Failed to save opt.yaml: {e}")

    # Load model
    device = select_device(device)
    model = DetectMultiBackend(weights, device=device, dnn=dnn, data=data, fp16=half)
    stride, names, pt = model.stride, model.names, model.pt
    imgsz = check_img_size(imgsz, s=stride)  # check image size

    # Dataloader
    bs = 1  # batch_size
    if webcam:
        view_img = check_imshow(warn=True)
        dataset = LoadStreams(source, img_size=imgsz, stride=stride, auto=pt, vid_stride=vid_stride)
        bs = len(dataset)
    elif screenshot:
        dataset = LoadScreenshots(source, img_size=imgsz, stride=stride, auto=pt)
    else:
        dataset = LoadImages(source, img_size=imgsz, stride=stride, auto=pt, vid_stride=vid_stride)
    vid_path, vid_writer = [None] * bs, [None] * bs

    # Run inference
    model.warmup(imgsz=(1 if pt else bs, 3, *imgsz))  # warmup
    seen, windows, dt = 0, [], (Profile(device=device), Profile(device=device), Profile(device=device))

    all_results = []

    for path, im, im0s, vid_cap, s in dataset:
        im0 = im0s.copy()
        gray_im = cv2.cvtColor(im0, cv2.COLOR_BGR2GRAY)

        # 添加图像统计信息分析
        analyze_image_statistics(gray_im, im0)

        with dt[0]:
            im = torch.from_numpy(im).to(model.device)
            im = im.half() if model.fp16 else im.float()  # uint8 to fp16/32
            im /= 255  # 0 - 255 to 0.0 - 1.0
            if len(im.shape) == 3:
                im = im[None]  # expand for batch dim

        # Inference
        with dt[1]:
            visualize = increment_path(save_dir / Path(path).stem, mkdir=True) if visualize else False
            pred, proto = model(im, augment=augment, visualize=visualize)[:2]

        # NMS
        with dt[2]:
            agnostic_nms = True
            pred = non_max_suppression(pred, conf_thres, iou_thres, classes, agnostic_nms, max_det=max_det, nm=32)

        # Process predictions
        for i, det in enumerate(pred):  # per image
            seen += 1
            if webcam:  # batch_size >= 1
                p, im0, frame = path[i], im0s[i].copy(), dataset.count
                s += f"{i}: "
            else:
                p, im0, frame = path, im0s.copy(), getattr(dataset, "frame", 0)

            p = Path(p)  # to Path
            save_path = str(save_dir / p.name)  # im.jpg
            txt_path = str(save_dir / "labels" / p.stem) + ("" if dataset.mode == "image" else f"_{frame}")  # im.txt
            s += "%gx%g " % im.shape[2:]  # print string
            imc = im0.copy() if save_crop else im0  # for save_crop
            annotator = Annotator(im0, line_width=line_thickness, example=str(names))

            if len(det):
                if retina_masks:
                    # scale bbox first the crop masks
                    det[:, :4] = scale_boxes(im.shape[2:], det[:, :4], im0.shape).round()  # rescale boxes to im0 size
                    masks = process_mask_native(proto[i], det[:, 6:], det[:, :4], im0.shape[:2])  # HWC
                else:
                    masks = process_mask(proto[i], det[:, 6:], det[:, :4], im.shape[2:], upsample=True)  # HWC
                    det[:, :4] = scale_boxes(im.shape[2:], det[:, :4], im0.shape).round()  # rescale boxes to im0 size

                # Segments
                if save_txt:
                    segments = [
                        scale_segments(im0.shape if retina_masks else im.shape[2:], x, im0.shape, normalize=True)
                        for x in reversed(masks2segments(masks))
                    ]

                # Print results
                for c in det[:, 5].unique():
                    n = (det[:, 5] == c).sum()  # detections per class
                    s += f"{n} {names[int(c)]}{'s' * (n > 1)}, "  # add to string

                # Mask plotting
                annotator.masks(
                    masks,
                    colors=[colors(x, True) for x in det[:, 5]],
                    im_gpu=torch.as_tensor(im0, dtype=torch.float16).to(device).permute(2, 0, 1).flip(0).contiguous()
                           / 255
                    if retina_masks
                    else im[i],
                )

                # ========= 干扰斑点遮盖 + 二次推理（以第一个点为基准）=========
                boxes_np = det[:, :4].cpu().numpy().astype(int)
                y_ref = choose_reference_y_from_boxes_xyxy(boxes_np, y_tolerance=y_tolerance)

                det_use, masks_use, im0_use, gray_use = det, masks, im0, gray_im

                # 如果检测到的点太少（少于3个），不启用遮盖，避免误遮盖
                if mask_interference and y_ref is not None and len(boxes_np) >= 3:
                    # 调试信息：显示遮盖范围
                    y_centers_all = (boxes_np[:, 1] + boxes_np[:, 3]) / 2.0
                    in_band_count = np.sum(np.abs(y_centers_all - float(y_ref)) <= float(y_tolerance))
                    LOGGER.info(f"Mask debug: y_ref={y_ref}, y_tolerance={y_tolerance}, "
                              f"boxes in band={in_band_count}/{len(boxes_np)}, "
                              f"band=[{y_ref - y_tolerance}, {y_ref + y_tolerance}]")
                    # 自动计算 x_limit：用"同一水平线内"的斑点最右边界，保护其右侧区域不被遮盖
                    x_limit = None
                    try:
                        y_centers = (boxes_np[:, 1] + boxes_np[:, 3]) / 2.0
                        in_band = np.abs(y_centers - float(y_ref)) <= float(y_tolerance)
                        if np.any(in_band):
                            x_limit = int(np.max(boxes_np[in_band, 2]) + int(mask_x_margin))
                    except Exception:
                        x_limit = None

                    im0_masked = mask_outside_band(
                        im0_bgr=im0,
                        boxes_xyxy=boxes_np,
                        y_ref=y_ref,
                        y_tolerance=y_tolerance,
                        pad=mask_pad,
                        color_mode=mask_color,
                        x_limit=x_limit,
                    )

                    if mask_save:
                        masked_path = str(save_dir / f"{p.stem}_masked.jpg")
                        cv2.imwrite(masked_path, im0_masked)

                    # 二次推理：在遮盖后的图上重新检测
                    im2_np, _ = preprocess_im0_for_model(im0_masked, imgsz, stride=stride, auto=pt)
                    im2 = torch.from_numpy(im2_np).to(model.device)
                    im2 = im2.half() if model.fp16 else im2.float()
                    im2 /= 255
                    if len(im2.shape) == 3:
                        im2 = im2[None]

                    pred2, proto2 = model(im2, augment=augment, visualize=False)[:2]
                    # 第二遍推理适当放宽置信度阈值，尽量找出弱斑点
                    conf_thres_second = min(conf_thres * 0.5, 0.2)
                    # 与第一遍保持一致：第5个参数为 agnostic_nms(位置参数)
                    pred2 = non_max_suppression(
                        pred2, conf_thres_second, iou_thres, classes, True, max_det=max_det, nm=32
                    )

                    # 只处理当前图片这一张（batch=1）
                    det2 = pred2[0]
                    if det2 is not None and len(det2):
                        det2[:, :4] = scale_boxes(im2.shape[2:], det2[:, :4], im0_masked.shape).round()
                        if retina_masks:
                            masks2 = process_mask_native(proto2[0], det2[:, 6:], det2[:, :4], im0_masked.shape[:2])
                        else:
                            masks2 = process_mask(proto2[0], det2[:, 6:], det2[:, :4], im2.shape[2:], upsample=True)

                        det_use, masks_use = det2, masks2
                        im0_use = im0_masked
                        gray_use = cv2.cvtColor(im0_use, cv2.COLOR_BGR2GRAY)

                # 使用增强的斑点处理函数
                spots_results = process_spots_sorted(det_use, masks_use, gray_use, im0_use, fixed_width, fixed_height, y_tolerance)

                # 手动多框补标：在自动识别结果基础上补漏检点
                # 部分笔记本 OpenCV 弹窗会闪退，失败则自动跳过
                manual_rects = []
                if manual_mark:
                    try:
                        manual_base = im0.copy()
                        for r in spots_results:
                            cx, cy = int(r["X_Position"]), int(r["Y_Position"])
                            x1, y1, x2, y2 = rect_from_center(cx, cy, fixed_width, fixed_height, im0.shape[1], im0.shape[0])
                            cv2.rectangle(manual_base, (x1, y1), (x2, y2), (0, 255, 0), 2)
                            cv2.putText(manual_base, "AUTO", (x1, max(15, y1 - 5)),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

                        LOGGER.info("Manual mark: Left-click = ADD, Right-click = DELETE, S = save, Esc = skip")
                        print(f"\nOpening Manual Mark window for: {p.name}")
                        print("Click the image window to focus it, then follow the on-screen instructions.")
                        print("Left-click = ADD  |  Right-click = DELETE  |  S = next  |  Esc = skip")
                        manual_rects = select_manual_rectangles(
                            manual_base,
                            window_name=f"Manual Mark - {p.name}",
                            fixed_width=fixed_width,
                            fixed_height=fixed_height,
                        )
                        if manual_rects:
                            manual_results = process_manual_rectangles(
                                gray_im=gray_im,
                                color_im=im0,
                                manual_rects=manual_rects,
                                start_spot_idx=len(spots_results),
                                fixed_width=fixed_width,
                                fixed_height=fixed_height,
                            )
                            spots_results.extend(manual_results)

                        if manual_save_json:
                            manual_json = {
                                "image": p.name,
                                "timestamp": datetime.now().isoformat(timespec="seconds"),
                                "manual_rects_xyxy": manual_rects,
                                "count": len(manual_rects),
                            }
                            with open(save_dir / f"{p.stem}_manual_rects.json", "w", encoding="utf-8") as f:
                                json.dump(manual_json, f, ensure_ascii=False, indent=2)
                    except Exception as e:
                        LOGGER.error(f"Manual mark window failed; skipped: {e}")
                        print(f"[Warning] Manual mark unavailable ({e}); continuing with auto detection.")
                        try:
                            cv2.destroyAllWindows()
                        except Exception:
                            pass

                spots_results = sorted(spots_results, key=lambda x: x["X_Position"])
                for new_idx, item in enumerate(spots_results):
                    item["Spot_Index"] = new_idx

                # 一维峰面积（色谱峰思路）：在最终斑点列表上统一计算
                if spots_results:
                    polarity = spots_results[0].get("Signal_Polarity") or detect_signal_polarity(
                        [r["Mean_Gray"] for r in spots_results],
                        float(spots_results[0].get("Lane_Background", np.median(gray_use))),
                    )
                    lane_bg = float(spots_results[0].get("Lane_Background", np.median(gray_use)))
                    half_h = max(8, int(fixed_height // 2))
                    attach_1d_peak_areas(
                        spots_results,
                        gray_use,
                        band_half_height=half_h,
                        polarity=polarity,
                        lane_bg=lane_bg,
                        default_half_width=max(20, int(fixed_width // 2)),
                        profile_save_path=None,
                    )

                # 为每个结果添加图像名称
                for result in spots_results:
                    result["Image"] = p.name
                    all_results.append(result)

                # ========== 标准曲线计算和浓度定量 ==========
                # 支持每张图片使用不同浓度（从 user_input/标准品浓度.csv 读取）
                image_conc = standard_conc
                image_standard_num = standard_num
                if concentrations_by_image:
                    from utils.load_user_config import get_concentrations_for_image
                    image_conc = get_concentrations_for_image(concentrations_by_image, p.name)
                    image_standard_num = len(image_conc)
                    LOGGER.info(f"Image [{p.name}] standard concentrations: {image_conc}")
                    if image_conc == concentrations_by_image.get("_default", standard_conc):
                        LOGGER.warning(
                            f"Image [{p.name}] not in concentration table; using (default) row. "
                            f"Expected filename in table: {p.name}"
                        )

                if len(spots_results) > image_standard_num:
                    # 分离标准品和样品
                    standard_results = spots_results[:image_standard_num]
                    sample_results = spots_results[image_standard_num:]

                    # 为标准品添加已知浓度
                    for i, result in enumerate(standard_results):
                        if i < len(image_conc):
                            result["Spot_Type"] = "standard"
                            result["Known_Concentration"] = image_conc[i]

                    # 为样品标记类型
                    for result in sample_results:
                        result["Spot_Type"] = "sample"

                    # 论文优先 IGI/IOD；366nm 时 IGI 退化则备选 peak_1d
                    background_type = resolve_imaging_profile(imaging_mode, im0)
                    conc_for_fit = image_conc[:len(standard_results)]
                    image_y_axis_type, image_y_label, axis_source, spearman_abs = select_paper_response_axis(
                        standard_results, conc_for_fit, background_type
                    )

                    LOGGER.info(
                        f"imaging_mode={imaging_mode}, background={background_type} "
                        f"({'366nm' if background_type == 'blue' else 'visible/254nm'})"
                    )
                    LOGGER.info(
                        f"Response axis: {image_y_label} ({image_y_axis_type}, source={axis_source}), "
                        f"|Spearman|={spearman_abs:.3f}"
                    )
                    print(
                        f"imaging_mode={imaging_mode} -> background={background_type} -> "
                        f"axis={image_y_label} [{axis_source}] (|Spearman|={spearman_abs:.3f})"
                    )

                    for result in spots_results:
                        result["Background_Type"] = background_type
                        result["Calibration_Y_Axis"] = image_y_axis_type
                        result["Response_Axis_Source"] = axis_source
                        result["Imaging_Mode"] = imaging_mode

                    try:
                        calibration_params, r_squared = calculate_calibration_curve_quadratic(
                            standard_results,
                            conc_for_fit,
                            y_axis_type=image_y_axis_type,
                            y_label=image_y_label,
                            quantification_method=quantification_method,
                        )
                        calibration_params["background_type"] = background_type
                        # 若浓度顺序被自动翻转，同步回写到 conc_for_fit 用于绘图
                        plot_conc = calibration_params.get("X_original", conc_for_fit)

                        sample_results = calculate_sample_concentrations_quadratic(sample_results, calibration_params)

                        for result in spots_results:
                            result["Calibration_R2"] = float(calibration_params.get("r_squared", r_squared))
                            iso_r2 = calibration_params.get("r_squared_isotonic")
                            if iso_r2 is not None and float(iso_r2) >= 0:
                                result["Calibration_R2_Isotonic"] = float(iso_r2)
                            result["Quantification_Method"] = calibration_params.get(
                                "quantification_method", quantification_method
                            )
                            result["Calibration_Y_Min"] = float(calibration_params.get("y_min", 0.0))
                            result["Calibration_Y_Max"] = float(calibration_params.get("y_max", 0.0))
                            result["Calibration_Conc_Min"] = float(calibration_params.get("conc_min", 0.0))
                            result["Calibration_Conc_Max"] = float(calibration_params.get("conc_max", 0.0))
                            if result.get("Spot_Type") == "standard":
                                result["Out_of_Range"] = False
                                result["Range_Status"] = "standard_reference"
                                result["Response_In_Range"] = True
                                result["Concentration_In_Range"] = True

                        calibration_plot_path = save_dir / f"{p.stem}_calibration_curve.png"
                        plot_calibration_curve_quadratic(
                            standard_results,
                            plot_conc,
                            calibration_params,
                            r_squared,
                            calibration_plot_path,
                            background_type=background_type,
                        )

                        a, b, c = calibration_params["a"], calibration_params["b"], calibration_params["c"]
                        LOGGER.info(f"Calibration complete: R2 = {r_squared:.6f}")
                        LOGGER.info(
                            f"Calibration: {image_y_label} = {a:.6f}*conc^2 + {b:.6f}*conc + {c:.6f}"
                        )
                        LOGGER.info(
                            f"Background: {background_type}, Y-axis: {image_y_label}, "
                            f"quantification={calibration_params.get('quantification_method')}, "
                            f"isotonic={calibration_params.get('use_isotonic')}, "
                            f"order_reversed={calibration_params.get('order_reversed')}"
                        )

                        polarity = standard_results[0].get("Signal_Polarity", "")
                        lane_bg = standard_results[0].get("Lane_Background", "")
                        print(
                            f"\n=== Quantification (polarity={polarity}, lane_bg={lane_bg}, axis={image_y_label}) ==="
                        )
                        print("Standards:")
                        for result in standard_results:
                            y_value = _extract_y_value(result, image_y_axis_type)
                            print(
                                f"  Spot {result['Spot_Index']}: conc={result['Known_Concentration']:.10f}, "
                                f"{image_y_label}={y_value:.4f}"
                            )

                        print("Samples:")
                        for result in sample_results:
                            y_value = _extract_y_value(result, image_y_axis_type)
                            oOR = result.get("Out_of_Range", False)
                            flag = " [out of range]" if oOR else ""
                            status = result.get("Range_Status", "")
                            print(
                                f"  Spot {result['Spot_Index']}: calc conc={result['Calculated_Concentration']:.10f}, "
                                f"{image_y_label}={y_value:.4f}, method={result.get('Concentration_Method')}"
                                f"{flag} ({status})"
                            )

                    except Exception as e:
                        LOGGER.error(f"Calibration failed: {e}")

                # 可视化：在图像上标注斑点序号和类型
                for result in spots_results:
                    center_x = result["X_Position"]
                    center_y = result["Y_Position"]
                    spot_index = result["Spot_Index"]
                    spot_type = result.get("Spot_Type", "unknown")
                    spot_source = result.get("Spot_Source", "auto")

                    # 根据斑点类型选择颜色
                    if spot_type == "standard":
                        color = (0, 255, 0)  # 绿色-标准品
                        label = f"S{spot_index}"
                    elif spot_type == "sample":
                        color = (255, 0, 0)  # 红色-样品
                        label = f"Sample{spot_index}"
                    else:
                        color = (0, 0, 255)  # 蓝色-未知
                        label = f"{spot_index}"

                    if spot_source == "manual":
                        color = (0, 255, 255)  # 黄色-手动补标
                        label = f"M{spot_index}"

                    # 在斑点中心标注序号和类型
                    cv2.putText(im0, label,
                                (center_x - 15, center_y - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                    # 自动与手动补标均使用相同固定框大小
                    start_x = center_x - fixed_width // 2
                    start_y = center_y - fixed_height // 2
                    end_x = start_x + fixed_width
                    end_y = start_y + fixed_height

                    cv2.rectangle(im0,
                                  (start_x, start_y),
                                  (end_x, end_y),
                                  color, 2)

                # Write results
                for j, (*xyxy, conf, cls) in enumerate(reversed(det[:, :6])):
                    if save_txt:  # Write to file
                        seg = segments[j].reshape(-1)  # (n,2) to (n*2)
                        line = (cls, *seg, conf) if save_conf else (cls, *seg)  # label format
                        with open(f"{txt_path}.txt", "a") as f:
                            f.write(("%g " * len(line)).rstrip() % line + "\n")

                    if save_img or save_crop or view_img:  # Add bbox to image
                        c = int(cls)  # integer class
                        label = None if hide_labels else (names[c] if hide_conf else f"{names[c]} {conf:.2f}")
                        # annotator.box_label(xyxy, label, color=colors(c, True))
                        # annotator.draw.polygon(segments[j], outline=colors(c, True), width=3)
                    if save_crop:
                        save_one_box(xyxy, imc, file=save_dir / "crops" / names[c] / f"{p.stem}.jpg", BGR=True)

            # Stream results
            im0 = annotator.result()
            if view_img:
                if platform.system() == "Linux" and p not in windows:
                    windows.append(p)
                    cv2.namedWindow(str(p), cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)  # allow window resize (Linux)
                    cv2.resizeWindow(str(p), im0.shape[1], im0.shape[0])
                cv2.imshow(str(p), im0)
                if cv2.waitKey(1) == ord("q"):  # 1 millisecond
                    exit()

            # Save results (image with detections)
            if save_img:
                if dataset.mode == "image":
                    cv2.imwrite(save_path, im0)
                else:  # 'video' or 'stream'
                    if vid_path[i] != save_path:  # new video
                        vid_path[i] = save_path
                        if isinstance(vid_writer[i], cv2.VideoWriter):
                            vid_writer[i].release()  # release previous video writer
                        if vid_cap:  # video
                            fps = vid_cap.get(cv2.CAP_PROP_FPS)
                            w = int(vid_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                            h = int(vid_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        else:  # stream
                            fps, w, h = 30, im0.shape[1], im0.shape[0]
                        save_path = str(Path(save_path).with_suffix(".mp4"))  # force *.mp4 suffix on results videos
                        vid_writer[i] = cv2.VideoWriter(save_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
                    vid_writer[i].write(im0)

        # Print time (inference-only)
        LOGGER.info(f"{s}{'' if len(det) else '(no detections), '}{dt[1].dt * 1E3:.1f}ms")

    # Print results
    t = tuple(x.t / seen * 1e3 for x in dt)  # speeds per image
    LOGGER.info(f"Speed: %.1fms pre-process, %.1fms inference, %.1fms NMS per image at shape {(1, 3, *imgsz)}" % t)
    if save_txt or save_img:
        s = f"\n{len(list(save_dir.glob('labels/*.txt')))} labels saved to {save_dir / 'labels'}" if save_txt else ""
        LOGGER.info(f"Results saved to {colorstr('bold', save_dir)}{s}")

    if all_results:
        df = pd.DataFrame(all_results)
        # 按图像名称和斑点索引排序
        df = df.sort_values(['Image', 'Spot_Index'])

        # 设置pandas显示选项以确保高精度
        pd.set_option('display.float_format', '{:.10f}'.format)

        # 对于浓度列，确保高精度保存
        if 'Known_Concentration' in df.columns:
            df['Known_Concentration'] = df['Known_Concentration'].astype(float)
        if 'Calculated_Concentration' in df.columns:
            df['Calculated_Concentration'] = df['Calculated_Concentration'].astype(float)

        # 保存详细结果到Excel；浓度关键列加粗，便于查看
        excel_path = save_dir / "quantitative_analysis_all_images.xlsx"
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, float_format="%.10f")
            try:
                from openpyxl.styles import Font

                ws = writer.sheets.get("Sheet1") or next(iter(writer.sheets.values()))
                bold = Font(bold=True)
                highlight_cols = {"Known_Concentration", "Calculated_Concentration"}
                for col_idx, col_name in enumerate(df.columns, start=1):
                    if col_name not in highlight_cols:
                        continue
                    for row_idx in range(1, len(df) + 2):  # header + data
                        ws.cell(row=row_idx, column=col_idx).font = bold
            except Exception as e:
                LOGGER.warning(f"Could not bold concentration columns in Excel: {e}")
        LOGGER.info(f"Saved quantitative analysis to {excel_path}")

        # 打印每个图像的斑点顺序和灰度值用于验证
        print("\n=== Spot order and gray values ===")
        for image_name in df['Image'].unique():
            image_data = df[df['Image'] == image_name]
            print(f"Image: {image_name}")
            for _, row in image_data.iterrows():
                spot_type = row.get('Spot_Type', 'unknown')
                conc_info = ""
                if spot_type == "standard" and pd.notna(row.get('Known_Concentration')):
                    conc_info = f", known conc={row['Known_Concentration']:.10f}"
                elif spot_type == "sample" and pd.notna(row.get('Calculated_Concentration')):
                    conc_info = f", calc conc={row['Calculated_Concentration']:.10f}"

                print(
                    f"  Spot {row['Spot_Index']}({spot_type}): mean gray={row['Mean_Gray']}, "
                    f"raw sum={row['Sum_Gray']}, corrected sum={row.get('Sum_Gray_Corrected', row['Sum_Gray'])}, "
                    f"total OD={row['Sum_OD']:.4f}{conc_info}")

    if update:
        strip_optimizer(weights[0])  # update model (to fix SourceChangeWarning)


def parse_opt():
    """Parses command-line options for YOLOv5 inference including model paths, data sources, inference settings, and
    output preferences.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", nargs="+", type=str, default=str(ROOT / "weights/best.pt"),
                        help="model path(s)")
    parser.add_argument("--source", type=str, default=str(ROOT / "user_input/images"),
                        help="file/dir/URL/glob/screen/0(webcam)")
    parser.add_argument("--data", type=str, default=str(ROOT / "weights/boCenColor.yaml"),
                        help="(optional) dataset.yaml path")
    parser.add_argument("--imgsz", "--img", "--img-size", nargs="+", type=int, default=[640], help="inference size h,w")
    parser.add_argument("--conf-thres", type=float, default=0.15, help="confidence threshold (lower = more sensitive, default: 0.15)")
    parser.add_argument("--iou-thres", type=float, default=0.3, help="NMS IoU threshold")
    parser.add_argument("--max-det", type=int, default=1000, help="maximum detections per image")
    parser.add_argument("--device", default="", help="cuda device, i.e. 0 or 0,1,2,3 or cpu")
    parser.add_argument("--view-img", action="store_true", help="show results")
    parser.add_argument("--save-txt", action="store_true", help="save results to *.txt")
    parser.add_argument("--save-conf", action="store_true", help="save confidences in --save-txt labels")
    parser.add_argument("--save-crop", action="store_true", help="save cropped prediction boxes")
    parser.add_argument("--nosave", action="store_true", help="do not save images/videos")
    parser.add_argument("--classes", nargs="+", type=int, help="filter by class: --classes 0, or --classes 0 2 3")
    parser.add_argument("--agnostic-nms", action="store_true", help="class-agnostic NMS")
    parser.add_argument("--augment", action="store_true", help="augmented inference")
    parser.add_argument("--visualize", action="store_true", help="visualize features")
    parser.add_argument("--update", action="store_true", help="update all models")
    parser.add_argument("--project", default=ROOT / "runs/predict-seg", help="save results to project/name")
    parser.add_argument("--name", default="exp", help="save results to project/name")
    parser.add_argument("--exist-ok", action="store_true", help="existing project/name ok, do not increment")
    parser.add_argument("--line-thickness", default=3, type=int, help="bounding box thickness (pixels)")
    parser.add_argument("--hide-labels", default=False, action="store_true", help="hide labels")
    parser.add_argument("--hide-conf", default=False, action="store_true", help="hide confidences")
    parser.add_argument("--half", action="store_true", help="use FP16 half-precision inference")
    parser.add_argument("--dnn", action="store_true", help="use OpenCV DNN for ONNX inference")
    parser.add_argument("--vid-stride", type=int, default=1, help="video frame-rate stride")
    parser.add_argument("--retina-masks", action="store_true", help="whether to plot masks in native resolution")
    # 添加固定长宽参数
    parser.add_argument("--fixed-width", type=int, default=130,
                        help="width of the rectangular region (e.g., 30 pixels)")
    parser.add_argument("--fixed-height", type=int, default=35,
                        help="height of the rectangular region (e.g., 20 pixels)")
    # 新增标准曲线参数
    parser.add_argument("--standard-num", type=int, default=5,
                        help="number of standard spots (concentration known)")
    parser.add_argument("--standard-concentrations", type=str, default="0.125,0.2,0.25,0.5,1",
                        help="comma separated concentrations of standard spots (supports up to 10 decimal places)")
    # 新增纵坐标类型参数
    parser.add_argument("--y-axis-type", type=str, default="sum_od",  # 修改：默认使用总光密度值
                        choices=["sum_gray", "mean_gray", "sum_od", "mean_od"],
                        help="type of y-axis for calibration curve")
    # 新增数据变换参数
    parser.add_argument("--transform-type", type=str, default="auto",
                        choices=["none", "log", "sqrt", "reciprocal", "log_log", "power", "auto"],
                        help="data transformation type to enhance linearity")
    parser.add_argument("--quantification-method", type=str, default="isotonic",
                        choices=["isotonic", "quadratic"],
                        help="concentration back-calculation: isotonic (default) or quadratic (paper reproduction)")
    # 新增：遮盖水平线外干扰斑点后二次推理（默认启用）
    parser.add_argument("--mask-interference", action="store_true", default=True,
                        help="mask spots outside the reference horizontal band and re-run inference (default: True)")
    parser.add_argument("--no-mask-interference", dest="mask_interference", action="store_false",
                        help="disable mask interference (opposite of --mask-interference)")
    parser.add_argument("--mask-color", type=str, default="background",
                        choices=["background", "white", "black"],
                        help="solid color used to cover interference spots")
    parser.add_argument("--mask-pad", type=int, default=6,
                        help="padding pixels added around interference boxes when masking")
    parser.add_argument("--mask-save", action="store_true", default=True,
                        help="save masked intermediate images for debugging (default: True)")
    parser.add_argument("--no-mask-save", dest="mask_save", action="store_false",
                        help="disable saving masked images (opposite of --mask-save)")
    parser.add_argument("--mask-x-margin", type=int, default=30,
                        help="auto x-limit margin to protect the right strip area from masking")
    parser.add_argument("--y-tolerance", type=int, default=60,
                        help="horizontal band tolerance (pixels) for judging if spots are on the same line (default: 60, larger = wider band)")
    parser.add_argument("--manual-mark", action="store_true", default=True,
                        help="enable manual rectangle marking for missed spots (default: True)")
    parser.add_argument("--no-manual-mark", dest="manual_mark", action="store_false",
                        help="disable manual rectangle marking")
    parser.add_argument("--manual-save-json", action="store_true", default=True,
                        help="save manual marked rectangles to json (default: True)")
    parser.add_argument("--no-manual-save-json", dest="manual_save_json", action="store_false",
                        help="disable saving manual marked rectangles json")
    opt = parser.parse_args()
    
    # 如果用户没有显式设置 mask_interference 和 mask_save，默认启用
    if "--mask-interference" not in sys.argv and "--no-mask-interference" not in sys.argv:
        opt.mask_interference = True
    if "--mask-save" not in sys.argv and "--no-mask-save" not in sys.argv:
        opt.mask_save = True
    if "--manual-mark" not in sys.argv and "--no-manual-mark" not in sys.argv:
        opt.manual_mark = True
    if "--manual-save-json" not in sys.argv and "--no-manual-save-json" not in sys.argv:
        opt.manual_save_json = True
    
    opt.imgsz *= 2 if len(opt.imgsz) == 1 else 1  # expand
    print_args(vars(opt))
    return opt


def main(opt):
    """Executes YOLOv5 model inference with given options, checking for requirements before launching."""
    check_requirements(ROOT / "requirements.txt", exclude=("tensorboard", "thop"))
    run(**vars(opt))


if __name__ == "__main__":
    opt = parse_opt()
    main(opt)
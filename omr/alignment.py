"""스캔 이미지 → 템플릿 좌표계 정렬.

스캔 과정에서 생기는 회전/이동/크기/기울어짐(원근) 왜곡을 보정한다.
ORB 특징점 매칭으로 호모그래피를 추정하고, 실패 시 외곽 사각형
(답안지 테두리) 검출로 폴백한다.
"""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from .template import Template


def _align_by_features(scan: np.ndarray, ref: np.ndarray) -> Optional[np.ndarray]:
    """ORB 특징점 매칭 기반 호모그래피 추정. 실패 시 None."""
    orb = cv2.ORB_create(nfeatures=4000)
    k1, d1 = orb.detectAndCompute(scan, None)
    k2, d2 = orb.detectAndCompute(ref, None)
    if d1 is None or d2 is None or len(k1) < 10 or len(k2) < 10:
        return None

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    matches = matcher.knnMatch(d1, d2, k=2)
    good = [m for pair in matches if len(pair) == 2
            for m, n in [pair] if m.distance < 0.75 * n.distance]
    if len(good) < 10:
        return None

    src = np.float32([k1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([k2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if H is None or mask is None or int(mask.sum()) < 8:
        return None
    return H


def _align_by_page_outline(scan: np.ndarray, ref_shape: tuple) -> Optional[np.ndarray]:
    """답안지 외곽 사각형을 찾아 원근 변환 추정. 실패 시 None."""
    blur = cv2.GaussianBlur(scan, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    page = max(contours, key=cv2.contourArea)
    if cv2.contourArea(page) < 0.3 * scan.shape[0] * scan.shape[1]:
        return None
    peri = cv2.arcLength(page, True)
    approx = cv2.approxPolyDP(page, 0.02 * peri, True)
    if len(approx) != 4:
        return None

    pts = approx.reshape(4, 2).astype(np.float32)
    # 좌상, 우상, 우하, 좌하 순 정렬
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    ordered = np.array([
        pts[np.argmin(s)], pts[np.argmin(d)],
        pts[np.argmax(s)], pts[np.argmax(d)],
    ], dtype=np.float32)

    h, w = ref_shape
    target = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]],
                      dtype=np.float32)
    return cv2.getPerspectiveTransform(ordered, target)


def align_to_template(scan_image, template: Template) -> np.ndarray:
    """스캔 이미지를 템플릿 기준 좌표계로 정렬해 그레이스케일로 반환.

    scan_image: 파일 경로(str) 또는 그레이스케일 ndarray.
    """
    if isinstance(scan_image, str):
        scan = cv2.imread(scan_image, cv2.IMREAD_GRAYSCALE)
        if scan is None:
            raise FileNotFoundError(f"이미지를 열 수 없습니다: {scan_image}")
    else:
        scan = scan_image
        if scan.ndim == 3:
            scan = cv2.cvtColor(scan, cv2.COLOR_BGR2GRAY)

    ref = template.load_reference()
    size = (template.width, template.height)

    H = _align_by_features(scan, ref)
    if H is not None:
        return cv2.warpPerspective(scan, H, size,
                                   flags=cv2.INTER_LINEAR,
                                   borderMode=cv2.BORDER_REPLICATE)

    M = _align_by_page_outline(scan, (template.height, template.width))
    if M is not None:
        return cv2.warpPerspective(scan, M, size,
                                   flags=cv2.INTER_LINEAR,
                                   borderMode=cv2.BORDER_REPLICATE)

    # 최후 수단: 단순 리사이즈 (스캔이 이미 정방향·전체 페이지인 경우)
    return cv2.resize(scan, size, interpolation=cv2.INTER_LINEAR)

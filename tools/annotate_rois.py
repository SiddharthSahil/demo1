# tools/annotate_rois.py
import cv2, json, os, sys

# ---------- CONFIG ----------
TEMPLATE_ID = "template1_Paste-Production-Base-Sheet"
IMG_PATH = os.path.join("templates", "template1_Paste-Production-Base-Sheet.png")  # put your file here
OUT_JSON = os.path.join("outputs", f"{TEMPLATE_ID}.json")

# Image size fit
MAX_DISPLAY_W = 1400   # fit-to-screen width
MAX_DISPLAY_H = 900    # fit-to-screen height


# 1) single (non-table) fields – draw rectangles in this exact order
HEADER_FIELDS = [
    "product",
    "sku",
    "batch_no",
    "incharge_sign",
    "posting_done_by",
]

# 2) table structure
TABLE_COLS = [
    "material",
    "line_no",
    "previous_batch_balance_qty",
    "total_received_qty_after_mrn",
    "packed_qty_fg",
    "loose_fg_qty",
    "sample",
    "rejection",
    "difference",
    "remark",
    "supervis_1",
    "supervis_2",
]
TABLE_ROWS = ["tube", "carton", "sleeve", "cld", "hanger"]  # data rows

# whether to include the leftmost printed labels column ("material") as an ROI
INCLUDE_MATERIAL_COLUMN = False
# ----------------------------

def draw_multi_rois(img, names, title):
    H, W = img.shape[:2]
    sx = min(MAX_DISPLAY_W / W, 1.0)
    sy = min(MAX_DISPLAY_H / H, 1.0)
    s = min(sx, sy)  # uniform scale
    disp = cv2.resize(img, (int(W * s), int(H * s))) if s < 1.0 else img

    print(f"\n==> Draw rectangles for: {', '.join(names)}")
    print("Instructions: drag a box for each field IN ORDER; press ENTER when done; press C to clear last.")

    cv2.namedWindow(title, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(title, disp.shape[1], disp.shape[0])
    rois_disp = cv2.selectROIs(title, disp, showCrosshair=True, fromCenter=False)
    cv2.destroyAllWindows()

    if len(rois_disp) != len(names):
        print(f"ERROR: expected {len(names)} boxes, got {len(rois_disp)}.")
        sys.exit(1)

    # rescale back to original coordinates
    out = []
    inv = 1.0 / s
    for n, (x, y, w, h) in zip(names, rois_disp):
        out.append({
            "field": n,
            "x": int(x * inv),
            "y": int(y * inv),
            "w": int(w * inv),
            "h": int(h * inv)
        })
    return out



_CLICKED = []

def _mouse_cb(event, x, y, flags, param):
    global _CLICKED
    if event == cv2.EVENT_LBUTTONDOWN:
        _CLICKED.append((x, y))

def collect_gridlines(img, axis="vertical", count_needed=None):
    """
    axis='vertical'  -> collect X positions of vertical grid lines (left to right), incl. outer borders
    axis='horizontal'-> collect Y positions of horizontal lines (top to bottom) for data rows incl. outer borders
    """
    global _CLICKED
    H, W = img.shape[:2]
    sx = min(MAX_DISPLAY_W / W, 1.0)
    sy = min(MAX_DISPLAY_H / H, 1.0)
    s = min(sx, sy)
    disp = cv2.resize(img, (int(W * s), int(H * s))) if s < 1.0 else img

    _CLICKED = []
    win = "Click grid lines"
    msg = ("LEFT→RIGHT click all VERTICAL gridlines (include outer borders). ENTER to finish."
           if axis == "vertical"
           else "TOP→BOTTOM click HORIZONTAL row borders (include top of row1 and bottom of last). ENTER to finish.")
    print("\n==> " + msg)

    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, disp.shape[1], disp.shape[0])
    cv2.setMouseCallback(win, _mouse_cb)
    # show a copy so clicks paint dots without distorting scaling
    screen = disp.copy()
    while True:
        # paint already clicked points
        for (cx, cy) in _CLICKED:
            cv2.circle(screen, (cx, cy), 4, (0, 255, 0), -1)
        cv2.imshow(win, screen)
        key = cv2.waitKey(20) & 0xFF
        if key in (13, 10):   # ENTER
            break
        if key == 27:         # ESC
            cv2.destroyAllWindows(); sys.exit(0)
        screen = disp.copy()
    cv2.destroyAllWindows()

    if not _CLICKED:
        print("No clicks captured."); sys.exit(1)

    inv = 1.0 / s
    if axis == "vertical":
        vals = sorted([int(cx * inv) for (cx, _) in _CLICKED])
    else:
        vals = sorted([int(cy * inv) for (_, cy) in _CLICKED])

    if count_needed and len(vals) != count_needed:
        print(f"WARNING: expected {count_needed} {axis} lines, got {len(vals)}; proceeding.")
    return vals


def main():
    if not os.path.exists(IMG_PATH):
        print(f"Image not found: {IMG_PATH}"); sys.exit(1)
    img = cv2.imread(IMG_PATH)
    if img is None:
        print("Failed to read image."); sys.exit(1)
    H, W = img.shape[:2]

    # 1) header fields (manual boxes)
    header_rois = draw_multi_rois(img, HEADER_FIELDS, "Draw header fields in order")

    # 2) grid lines for table
    # verticals: you should click ALL vertical lines for the table (left border first ... right border last).
    x_lines = collect_gridlines(img, axis="vertical")
    # horizontals: click TOP border of first data row ... BOTTOM border of last data row (so N_rows+1 clicks).
    y_lines = collect_gridlines(img, axis="horizontal")
    if len(y_lines) != len(TABLE_ROWS) + 1:
        print(f"NOTE: For {len(TABLE_ROWS)} rows you typically want {len(TABLE_ROWS)+1} horizontal clicks.")

    # build table cell rois
    table_rois = []
    col_indices = range(len(TABLE_COLS)) if INCLUDE_MATERIAL_COLUMN else range(1, len(TABLE_COLS))
    for ri in range(len(y_lines) - 1):
        row_name = TABLE_ROWS[ri] if ri < len(TABLE_ROWS) else f"row{ri+1}"
        y1, y2 = int(y_lines[ri]), int(y_lines[ri + 1])
        for ci in col_indices:
            if ci >= len(x_lines) - 1:
                continue
            col_name = TABLE_COLS[ci]
            x1, x2 = int(x_lines[ci]), int(x_lines[ci + 1])
            w, h = x2 - x1, y2 - y1
            field = f"{col_name}__{row_name}"
            table_rois.append({"field": field, "x": x1, "y": y1, "w": w, "h": h})

    # pack and save
    out = {
        "template_id": TEMPLATE_ID,
        "width": int(W),
        "height": int(H),
        "rois": header_rois + table_rois
    }
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved ROI JSON → {OUT_JSON}")
    print("Tip: run verify_rois.py next to visually confirm boxes.")

if __name__ == "__main__":
    main()

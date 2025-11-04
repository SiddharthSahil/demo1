# tools/verify_rois.py
import cv2, json, os, sys, argparse
from datetime import datetime

# -------- Display sizing (same idea as annotate script) --------
MAX_DISPLAY_W = 1400
MAX_DISPLAY_H = 900

def load_cfg(json_path):
    if not os.path.exists(json_path):
        print(f"JSON not found: {json_path}")
        sys.exit(1)
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)

def draw_all(img, rois, highlight_idx=None):
    """
    Draw all boxes. If highlight_idx is set, draw that ROI thicker.
    """
    vis = img.copy()
    for i, r in enumerate(rois):
        x,y,w,h = r["x"], r["y"], r["w"], r["h"]
        # yellow for all, blue for highlighted ROI
        color = (0, 255, 255) if i != highlight_idx else (255, 0, 0)
        thickness = 2 if i != highlight_idx else 3
        cv2.rectangle(vis, (x, y), (x+w, y+h), color, thickness)
        # label background
        label = r["field"]
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(vis, (x, max(0, y-18)), (x+tw+6, y-2), color, -1)
        cv2.putText(vis, label, (x+3, y-6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,0), 1, cv2.LINE_AA)
    return vis

def fit_for_display(img):
    H, W = img.shape[:2]
    sx = min(MAX_DISPLAY_W / W, 1.0)
    sy = min(MAX_DISPLAY_H / H, 1.0)
    s = min(sx, sy)
    if s < 1.0:
        disp = cv2.resize(img, (int(W*s), int(H*s)))
    else:
        disp = img
    return disp, s

def save_overlay(img, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cv2.imwrite(out_path, img)
    print(f"Saved overlay → {out_path}")

def main():
    ap = argparse.ArgumentParser(description="Verify ROI alignment on the full-resolution template.")
    ap.add_argument("--template_id", type=str, default=None, help="If provided, auto-pick paths by template id (outputs/<id>.json, templates/<id>.png).")
    ap.add_argument("--json", type=str, default=None, help="Path to ROI json.")
    ap.add_argument("--img", type=str, default=None, help="Path to template image.")
    ap.add_argument("--export", action="store_true", help="Save an annotated PNG in outputs/ for sharing.")
    args = ap.parse_args()

    if args.template_id:
        json_path = os.path.join("outputs", f"{args.template_id}.json")
        # try common file name patterns for the image
        candidates = [
            os.path.join("templates", f"{args.template_id}.png"),
            os.path.join("templates", f"{args.template_id}.jpg"),
            os.path.join("templates", f"{args.template_id}.jpeg"),
        ]
        img_path = next((p for p in candidates if os.path.exists(p)), None)
        if img_path is None:
            print("Could not find image for template_id; tried:")
            print("\n".join(candidates)); sys.exit(1)
    else:
        if not args.json or not args.img:
            print("Provide either --template_id <id> OR both --json and --img.")
            sys.exit(1)
        json_path, img_path = args.json, args.img

    cfg = load_cfg(json_path)
    if not os.path.exists(img_path):
        print(f"Image not found: {img_path}"); sys.exit(1)

    img = cv2.imread(img_path)
    if img is None:
        print("Failed to read image."); sys.exit(1)

    # sanity vs JSON
    H, W = img.shape[:2]
    if "width" in cfg and "height" in cfg and (cfg["width"] != W or cfg["height"] != H):
        print(f"WARNING: Image size ({W}x{H}) differs from JSON ({cfg['width']}x{cfg['height']}).")
        print("If this is a scanned copy with different size, you must add a preprocessor (deskew+resize) before cropping.")

    rois = cfg.get("rois", [])
    if not rois:
        print("No ROIs found in JSON."); sys.exit(1)

    # draw and show (with highlight navigation)
    vis = draw_all(img, rois, highlight_idx=None)
    disp, s = fit_for_display(vis)
    win = f"Verify ROIs - {cfg.get('template_id','unknown')}"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, disp.shape[1], disp.shape[0])

    idx = 0  # no highlight initially
    print("\nControls: ←/→ to highlight prev/next ROI, 'e' to export overlay, 'q' or ESC to quit.")
    while True:
        # re-render if a highlight is set
        if idx >= 0:
            vis = draw_all(img, rois, highlight_idx=idx)
        else:
            vis = draw_all(img, rois, highlight_idx=None)
        disp, s = fit_for_display(vis)
        cv2.imshow(win, disp)
        key = cv2.waitKey(0)
        print("Key pressed:", key)

        if key in (27, ord('q')):   # ESC or q
            break
        if key == ord('e') and args.export:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = os.path.join("outputs", f"{cfg.get('template_id','template')}_overlay_{ts}.png")
            save_overlay(vis, out_path)
        
        # handle arrow keys (Windows / Linux both)
        if key in (ord('a'), ord('A')):   # previous ROI
            idx = (idx - 1) % len(rois)
        if key in (ord('d'), ord('D')):   # next ROI
            idx = (idx + 1) % len(rois)

    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()

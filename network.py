"""
network.py
Build an interactive card relationship graph (pyvis) from `network.yaml`.

Usage: run this script inside the project's virtualenv so required
dependencies (pyvis, pillow, pyyaml, requests) are available.

Outputs: `network.html` and cached images in the `images/` folder.
"""

import yaml
import os
import asyncio
from PIL import Image
import requests
from pyvis.options import Options
from pyvis.network import Network
import argparse
import re


# Reference crop parameters (based on 690x1000 example)
REF_W, REF_H = 690, 1000
REF_OFFSET = (82, 182)  # (x, y) in reference
REF_CROP_SIZE = (528, 522)  # (w, h) in reference

# Default colors for each operation
OPERATION_COLORS = {
    "series": "orange",
    "convergence": "purple",
    "parallel": "green",
    "divergence": "red",
}


# Node display settings
DEFAULT_NODE_SIZE = 100

# Registry of nodes already added to the graph
nodes = {}


def sanitize_card_name(name):
    """Sanitize card name for filenames (remove all non-alphanumeric characters)."""
    return re.sub(r"[^a-zA-Z0-9]", "", name)


def _download_card_images_fallback(card_names):
    """Fallback method to download and crop card images directly from Yugipedia API.

    Used when yugiquery utilities are unavailable. Saves images to `images/<Card_Name>.jpg`.
    Existing files are skipped.
    """
    image_dir = "images"
    if not os.path.exists(image_dir):
        os.makedirs(image_dir)

    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/116.0.0.0 Safari/537.36"
    }
    base_url = "https://yugipedia.com/api.php"

    for name in sorted(card_names):
        filename = f"{image_dir}/{sanitize_card_name(name)}.jpg"
        if os.path.exists(filename):
            continue  # Already downloaded
        # Query for the card's image via MediaWiki API
        params = {
            "action": "query",
            "format": "json",
            "prop": "pageimages",
            "titles": name,
            "piprop": "original",
        }
        try:
            resp = session.get(base_url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            data_json = resp.json()
            pages = data_json.get("query", {}).get("pages", {})
            # Find the image URL
            image_url = None
            for page in pages.values():
                original = page.get("original")
                thumbnail = page.get("thumbnail")
                if original and "source" in original:
                    image_url = original["source"]
                elif thumbnail and "original" in thumbnail:
                    image_url = thumbnail["original"]
            if not image_url:
                print(f"[WARN] No image found for '{name}'")
                continue
            # Download the image
            img_resp = session.get(image_url, headers=headers, timeout=10)
            img_resp.raise_for_status()

            # Open, crop, and save the image
            from io import BytesIO

            img = Image.open(BytesIO(img_resp.content))
            cropped_img = _crop_section(img, out_size=None)
            cropped_img.save(filename)
            print(f"Downloaded image for '{name}'")
        except Exception as e:
            print(f"[ERROR] Failed to download image for '{name}': {e}")


def _crop_section(
    im,
    *,
    ref=(REF_W, REF_H),
    offset=REF_OFFSET,
    crop_size=REF_CROP_SIZE,
    out_size=None,
):
    """Crop Yu-Gi-Oh card artwork section using aspect-ratio scaling.

    Args:
        im: PIL Image to crop.
        ref: Reference dimensions (width, height).
        offset: Crop offset (x, y) in reference dimensions.
        crop_size: Crop size (width, height) in reference dimensions.
        out_size: Optional resize dimensions.

    Returns:
        Cropped image in RGB mode.
    """
    w, h = im.size

    # Match reference aspect by center-cropping the original image if necessary
    ref_w, ref_h = ref
    ref_aspect = ref_w / ref_h
    aspect = w / h
    if abs(aspect - ref_aspect) > 1e-6:
        if aspect > ref_aspect:
            # image is wider -> crop width
            new_w = int(round(h * ref_aspect))
            new_w = min(new_w, w)
            left = max(0, (w - new_w) // 2)
            right = left + new_w
            im = im.crop((left, 0, right, h))
        else:
            # image is taller -> crop height
            new_h = int(round(w / ref_aspect))
            new_h = min(new_h, h)
            top = max(0, (h - new_h) // 2)
            bottom = top + new_h
            im = im.crop((0, top, w, bottom))
        w, h = im.size

    # Compute ratios from reference
    ox = offset[0] / ref_w
    oy = offset[1] / ref_h
    cw = crop_size[0] / ref_w
    ch = crop_size[1] / ref_h

    left = int(round(ox * w))
    top = int(round(oy * h))
    right = left + int(round(cw * w))
    bottom = top + int(round(ch * h))

    # Clamp to image bounds and shift if necessary
    if right > w:
        right = w
        left = max(0, w - int(round(cw * w)))
    if bottom > h:
        bottom = h
        top = max(0, h - int(round(ch * h)))

    cropped = im.crop((left, top, right, bottom))
    if out_size:
        resampling = Image.Resampling.LANCZOS
        cropped = cropped.resize(out_size, resampling)
    if cropped.mode != "RGB":
        cropped = cropped.convert("RGB")

    return cropped


def download_card_images(card_names):
    """Download and crop card images from Yugipedia.

    Attempts yugiquery utilities first (async + featured images), falls back to direct API.
    Saves to `images/<Card_Name>.jpg`. Skips existing files.
    """
    # Try to use yugiquery
    try:
        from yugiquery.utils.api import fetch_featured_images, download_media
        from yugiquery.utils.image import crop_section as yugiquery_crop

        # Fetch the featured image filenames
        file_names = fetch_featured_images(*card_names)
        image_dir = "images"

        # Download them (only if we got filenames)
        if file_names:
            results = asyncio.run(download_media(*file_names, output_path=image_dir))

            # Print download results
            if results is not None and len(results) > 0:
                succeeded = [
                    r
                    for r in results
                    if isinstance(r, dict) and r.get("status") == "success"
                ]
                failed = [
                    r
                    for r in results
                    if isinstance(r, dict) and r.get("status") == "failed"
                ]
                print(
                    f"Downloaded {len(succeeded)}/{len(results)} images using yugiquery"
                )
                if failed:
                    for result in failed:
                        print(f"[WARN] Failed to download: {result.get('file_name')}")

            # Crop the downloaded images
            for name in card_names:
                filename = f"{image_dir}/{sanitize_card_name(name)}.jpg"
                if os.path.exists(filename):
                    try:
                        with Image.open(filename) as img:
                            cropped_img = yugiquery_crop(
                                img,
                                ref=(REF_W, REF_H),
                                offset=REF_OFFSET,
                                crop_size=REF_CROP_SIZE,
                                out_size=None,
                            )
                            cropped_img.save(filename)
                    except Exception as e:
                        print(f"[WARN] Failed to crop image for '{name}': {e}")
        else:
            print("[WARN] No image filenames found")
    except:
        print(
            "[WARN] yugiquery utilities unavailable, falling back to direct API method"
        )
        _download_card_images_fallback(card_names)


def add_card_node(name):
    """Add a card node to the network graph with its image."""
    if name not in nodes:
        nodes[name] = True
        net.add_node(
            name,
            title=name,
            shape="image",
            image=f"images/{sanitize_card_name(name)}.jpg",
            size=DEFAULT_NODE_SIZE,
            borderWidthSelected=4,
            shapeProperties={"useBorderWithImage": True},
        )


def add_edge(src, dst, operation, color=None):
    """Add a styled edge between nodes based on operation type.

    Args:
        src: Source node name.
        dst: Destination node name.
        operation: One of "series", "convergence", "parallel", "divergence".
        color: Optional color override (defaults to OPERATION_COLORS[operation]).
    """
    if color is None:
        color = OPERATION_COLORS[operation]

    # parallel edges are undirected; all others are directed
    arrows = "none" if operation == "parallel" else "to"
    # parallel edges should not be smooth
    smooth = operation != "parallel"

    net.add_edge(
        src,
        dst,
        color=color,
        title=operation,
        arrows=arrows,
        arrowStrikethrough=False,
        arrowScaleFactor=2,
        width=4,
        smooth=smooth,
    )


def build_graph(yaml_path):
    base_name = os.path.splitext(os.path.basename(yaml_path))[0]
    html_output = os.path.abspath(f"{base_name}.html")

    # Load YAML
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)
    all_cards = set()

    # Series (sequential transformations)
    for entry in data.get("series", []):
        cards = entry.get("cards", []) if isinstance(entry, dict) else entry
        for card in cards:
            all_cards.add(card)

    # Convergence (multiple materials -> product)
    for entry in data.get("convergence", []):
        for mat in entry.get("materials", []):
            all_cards.add(mat)
        all_cards.add(entry.get("product"))

    # Parallel (cards at same level)
    for entry in data.get("parallel", []):
        cards = entry.get("cards", []) if isinstance(entry, dict) else entry
        for card in cards:
            all_cards.add(card)

    # Divergence (root -> branches)
    for entry in data.get("divergence", []):
        root = entry.get("root")
        if root:
            all_cards.add(root)
        for branch in entry.get("branches", []):
            all_cards.add(branch)

    # Ensure all required card images exist
    download_card_images(all_cards)

    # Use viewport height so the network fills the browser window
    global net
    net = Network(height="100vh", width="100%", directed=True, select_menu=True)

    # --- Series edges (sequential transformations) ---
    for entry in data.get("series", []):
        if isinstance(entry, dict):
            cards = entry.get("cards", [])
            color = entry.get("color")
        else:
            cards = entry
            color = None
        for node in cards:
            add_card_node(node)
        for i in range(len(cards) - 1):
            add_edge(cards[i], cards[i + 1], "series", color=color)

    # --- Convergence edges (materials -> product) ---
    for entry in data.get("convergence", []):
        materials = entry.get("materials", [])
        product = entry.get("product")
        color = entry.get("color")
        for mat in materials:
            add_card_node(mat)
        add_card_node(product)
        for mat in materials:
            add_edge(mat, product, "convergence", color=color)

    # --- Parallel edges (cards at same level with undirected edges between consecutive members) ---
    for entry in data.get("parallel", []):
        if isinstance(entry, dict):
            cards = entry.get("cards", [])
            color = entry.get("color")
        else:
            cards = entry
            color = None
        for card in cards:
            add_card_node(card)
        for i in range(len(cards) - 1):
            add_edge(cards[i], cards[i + 1], "parallel", color=color)

    # --- Divergence edges (root -> branches) ---
    for entry in data.get("divergence", []):
        root = entry.get("root")
        branches = entry.get("branches", [])
        color = entry.get("color")
        if not root:
            continue
        add_card_node(root)
        for branch in branches:
            add_card_node(branch)
            add_edge(root, branch, "divergence", color=color)

    # Configure physics via a pyvis Options object so pyvis APIs still work.
    options_obj = Options()
    options_obj.physics.enabled = True
    options_obj.physics.use_repulsion(
        {
            "node_distance": 1000,
            "central_gravity": 0.2,
            "spring_length": 200,
            "spring_strength": 0.015,
            "damping": 0.09,
        }
    )
    net.options = options_obj

    net.show_buttons(filter_=["physics", "interaction"])
    net.write_html(html_output)
    print("Saved to:", html_output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build an interactive card relationship graph from a YAML file."
    )
    parser.add_argument("yaml_file", help="Path to the network YAML file.")
    args = parser.parse_args()
    build_graph(args.yaml_file)
else:
    # Default to 'network.yaml' if imported
    build_graph("network.yaml")

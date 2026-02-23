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


class AttrDict(dict):
    def __getattr__(self, name):
        value = self.get(name)
        if isinstance(value, dict):
            return AttrDict(value)
        return value

    def __setattr__(self, name, value):
        self[name] = value

    def __delattr__(self, name):
        del self[name]


class Config(AttrDict):
    def __init__(self, overrides=None):
        defaults = {
            "colors": {
                "series": "orange",
                "convergence": "purple",
                "parallel": "green",
                "divergence": "red",
            },
            "sizes": {
                "ref": (690, 1000),
                "offset": (82, 182),
                "crop": (528, 522),
                "node": 100,
            },
            "show_buttons": True,
            "buttons_filter": ["physics", "interaction"],
            "physics": {
                "enabled": True,
                "repulsion": {
                    "node_distance": 1000,
                    "central_gravity": 0.2,
                    "spring_length": 200,
                    "spring_strength": 0.015,
                    "damping": 0.09,
                },
            },
            "network": {
                "height": "90vh",
                "width": "100%",
                "directed": True,
                "select_menu": True,
            },
        }
        merged = self._deep_merge(defaults, overrides or {})
        super().__init__(merged)

    def _deep_merge(self, d, u):
        for k, v in u.items():
            if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                d[k] = self._deep_merge(d[k], v)
            else:
                d[k] = v
        return d


# Registry of nodes already added to the graph
nodes = set()


def sanitize_card_name(name):
    """Sanitize card name for filenames (remove all non-alphanumeric characters)."""
    return re.sub(r"[^a-zA-Z0-9]", "", name)


def _download_card_images_fallback(card_names, config):
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
            cropped_img = _crop_section(img, config=config, out_size=None)
            cropped_img.save(filename)
            print(f"Downloaded image for '{name}'")
        except Exception as e:
            print(f"[ERROR] Failed to download image for '{name}': {e}")


def _crop_section(
    im,
    *,
    config,
    out_size=None,
):
    w, h = im.size
    ref_w, ref_h = config.sizes.ref
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

    ox = config.sizes.offset[0] / ref_w
    oy = config.sizes.offset[1] / ref_h
    cw = config.sizes.crop[0] / ref_w
    ch = config.sizes.crop[1] / ref_h

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


def download_card_images(card_names, config):
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
                                ref=config.sizes.ref,
                                offset=config.sizes.offset,
                                crop_size=config.sizes.crop,
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
        _download_card_images_fallback(card_names, config)


def add_card_node(name, config, net):
    """Add a card node to the network graph with its image."""
    if name not in nodes:
        nodes.add(name)
        net.add_node(
            name,
            title=name,
            shape="image",
            image=f"images/{sanitize_card_name(name)}.jpg",
            size=config.sizes.node,
            borderWidthSelected=4,
            shapeProperties={"useBorderWithImage": True},
        )


def add_edge(src, dst, operation, config, net, color=None):
    """Add a styled edge between nodes based on operation type.

    Args:
        src: Source node name.
        dst: Destination node name.
        operation: One of "series", "convergence", "parallel", "divergence".
        color: Optional color override (defaults to OPERATION_COLORS[operation]).
    """
    if color is None:
        color = config.colors[operation]
    arrows = "none" if operation == "parallel" else "to"
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
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)
    raw_config = data.get("config", {})
    if isinstance(raw_config, list):
        merged_config = {}
        for entry in raw_config:
            if isinstance(entry, dict):
                merged_config.update(entry)
        raw_config = merged_config
    config = Config(raw_config)
    all_cards = set()
    for entry in data.get("series", []):
        cards = entry.get("cards", []) if isinstance(entry, dict) else entry
        for card in cards:
            all_cards.add(card)
    for entry in data.get("convergence", []):
        for mat in entry.get("materials", []):
            all_cards.add(mat)
        all_cards.add(entry.get("product"))
    for entry in data.get("parallel", []):
        cards = entry.get("cards", []) if isinstance(entry, dict) else entry
        for card in cards:
            all_cards.add(card)
    for entry in data.get("divergence", []):
        root = entry.get("root")
        if root:
            all_cards.add(root)
        for branch in entry.get("branches", []):
            all_cards.add(branch)
    download_card_images(all_cards, config)

    net = Network(**config.network)

    for entry in data.get("series", []):
        if isinstance(entry, dict):
            cards = entry.get("cards", [])
            color = entry.get("color")
        else:
            cards = entry
            color = None
        for node in cards:
            add_card_node(node, config, net)
        for i in range(len(cards) - 1):
            add_edge(cards[i], cards[i + 1], "series", config, net, color=color)
    for entry in data.get("convergence", []):
        materials = entry.get("materials", [])
        product = entry.get("product")
        color = entry.get("color")
        for mat in materials:
            add_card_node(mat, config, net)
        add_card_node(product, config, net)
        for mat in materials:
            add_edge(mat, product, "convergence", config, net, color=color)
    for entry in data.get("parallel", []):
        if isinstance(entry, dict):
            cards = entry.get("cards", [])
            color = entry.get("color")
        else:
            cards = entry
            color = None
        for card in cards:
            add_card_node(card, config, net)
        for i in range(len(cards) - 1):
            add_edge(cards[i], cards[i + 1], "parallel", config, net, color=color)
    for entry in data.get("divergence", []):
        root = entry.get("root")
        branches = entry.get("branches", [])
        color = entry.get("color")
        if not root:
            continue
        add_card_node(root, config, net)
        for branch in branches:
            add_card_node(branch, config, net)
            add_edge(root, branch, "divergence", config, net, color=color)

    options_obj = Options(config.options if "options" in config else {})
    options_obj.physics.enabled = config.physics.enabled
    options_obj.physics.use_repulsion(config.physics.repulsion)
    net.options = options_obj

    if config.show_buttons:
        net.show_buttons(filter_=config.buttons_filter)

    base_name = os.path.splitext(os.path.basename(yaml_path))[0]
    html_output = os.path.abspath(f"{base_name}.html")
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
    build_graph("network.yaml")

"""
network.py

Builds an interactive relationship network from a YAML configuration file using pyvis.

Features:
    - Visualizes card evolutions, fusions, parallels, and archetype branches.
    - Customizable edge colors, smoothness, and titles per relationship type.
    - Node size scales by degree (number of connections).
    - Card images downloaded and cropped automatically.
    - Interactive controls (physics, layout, navigation buttons).
    - Configurable via YAML for easy extension.

Usage:
    1. Run: python network.py network.yaml
    2. Open network.html in your browser.

Dependencies: pyvis, pillow, pyyaml, requests

Outputs:
    - network.html (interactive network visualization)
    - images/ (card images)
"""

import yaml
import os
import re
import asyncio
from PIL import Image
import requests
from pyvis.options import Options
from pyvis.network import Network
import argparse


# --- Filename sanitization utility ---


def image_filename(name):
    """
    Sanitize a card name for use as a filename by removing all non-alphanumeric characters.

    Args:
        name (str): Card name to sanitize.
    Returns:
        str: Sanitized filename string.
    """
    return re.sub(r"[^a-zA-Z0-9]", "", name)


# --- Image downloading and cropping utilities ---


def _crop_section(
    im,
    *,
    config,
    out_size=None,
):
    """
    Crop a PIL image to the configured section and optionally resize.

    Args:
        im (PIL.Image): Image to crop.
        config (Config): Configuration object with crop parameters.
        out_size (tuple or None): Optional output size (width, height).
    Returns:
        PIL.Image: Cropped and optionally resized image.
    """
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


def _download_images_fallback(names, config):
    """
    Download and crop card images directly from Yugipedia API (fallback method).
    Used when yugiquery utilities are unavailable. Saves images to images/<Card_Name>.jpg.
    Skips existing files.

    Args:
        names (Iterable[str]): Card names to download.
        config (Config): Configuration object for cropping.
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

    for name in sorted(names):
        filename = f"{image_dir}/{image_filename(name)}.jpg"
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


def download_images(names, config):
    """
    Download and crop card images from Yugipedia.
    Attempts yugiquery utilities first (async + featured images), falls back to direct API.
    Saves images to images/<Card_Name>.jpg. Skips existing files.

    Args:
        names (Iterable[str]): Card names to download.
        config (Config): Configuration object for cropping.
    """
    # Try to use yugiquery
    try:
        from yugiquery.utils.api import fetch_featured_images, download_media
        from yugiquery.utils.image import crop_section as yugiquery_crop

        # Fetch the featured image filenames
        file_names = fetch_featured_images(*names)
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
            for name in names:
                filename = f"{image_dir}/{image_filename(name)}.jpg"
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
        _download_images_fallback(names, config)


# --- Configuration utilities ---


class AttrDict(dict):
    """
    Dictionary subclass that allows attribute-style access to keys, recursively.
    Useful for deep config objects and YAML configs.
    """

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
    """
    Configuration object that merges user overrides with defaults and allows deep attribute access.
    Used for all visual and behavioral settings.
    """

    def __init__(self, overrides=None):
        defaults = {
            "node": {
                "scale": False,  # Toggle scaling node size by degree
                "scale_factor": 10,  # Factor for scaling node size by degree
                "shape": "image",
                "size": 100,
                "borderWidthSelected": 4,
                "shapeProperties": {"useBorderWithImage": True},
            },
            "edge": {"arrowStrikethrough": False, "width": 20},
            "operation": {
                "series": {"color": "orange", "smooth": True},
                "convergence": {"color": "purple", "smooth": True},
                "parallel": {"color": "green", "smooth": False},
                "divergence": {"color": "red", "smooth": True},
            },
            "sizes": {
                "ref": (690, 1000),
                "offset": (82, 182),
                "crop": (528, 522),
            },
            "buttons": {
                "show": False,
                "filter": ["physics", "interaction"],
            },
            "physics": {
                "enabled": True,
                "repulsion": {
                    "node_distance": 1000,
                    "central_gravity": 0.2,
                    "spring_length": 200,
                    "spring_strength": 0.015,
                    "damping": 0.50,
                },
            },
            "network": {
                "height": "90vh",
                "width": "100%",
                "directed": True,
                "select_menu": True,
            },
            "download_images": False,  # Toggle downloading images
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


# --- Options configuration utilities ---


def set_physics_options(physics_obj, config):
    """
    Apply physics-related configuration to the pyvis Physics object.
    Supports enabling/disabling physics, selecting solvers, and toggling stabilization.
    Sets additional attributes generically.
    """
    # Handle special keys with methods/logic
    if config.get("enabled") is not None:
        physics_obj.enabled = config["enabled"]
    else:
        physics_obj.enabled = True
    if config.get("repulsion"):
        physics_obj.use_repulsion(config["repulsion"])
    if config.get("forceAtlas2Based"):
        physics_obj.use_force_atlas_2based(config["forceAtlas2Based"])
    if config.get("barnesHut"):
        physics_obj.use_barnes_hut(config["barnesHut"])
    if config.get("hierarchicalRepulsion"):
        physics_obj.use_hrepulsion(config["hierarchicalRepulsion"])
    if config.get("stabilization") is not None:
        physics_obj.toggle_stabilization(bool(config["stabilization"]))

    # Set all other attributes generically
    handled = {
        "enabled",
        "repulsion",
        "forceAtlas2Based",
        "barnesHut",
        "hierarchicalRepulsion",
        "stabilization",
    }
    for attr, value in config.items():
        if attr in handled or value is None:
            continue
        setattr(physics_obj, attr, value)


def set_edge_options(edges_obj, config):
    """
    Apply edge-related configuration to the pyvis EdgeOptions object.
    Supports toggling smoothness type and color inheritance.
    Sets additional attributes generically.
    """
    # Handle special keys with methods/logic
    if config.get("smooth_type"):
        edges_obj.toggle_smoothness(config["smooth_type"])
    if config.get("inherit_colors") is not None:
        edges_obj.inherit_colors(config["inherit_colors"])

    # Set all other attributes generically
    handled = {"smooth_type", "inherit_colors"}
    for attr, value in config.items():
        if attr in handled or value is None:
            continue
        setattr(edges_obj, attr, value)


def set_layout_options(layout_obj, config):
    """
    Apply layout-related configuration to the pyvis Layout object.
    Supports random seed, improved layout, and hierarchical layout options.
    Sets additional attributes generically.
    """
    # Set all non-hierarchical attributes
    for attr, value in config.items():
        if attr == "hierarchical" or value is None:
            continue
        setattr(layout_obj, attr, value)

    # Handle hierarchical layout options
    hier = config.get("hierarchical")
    if hier:
        if hier.get("levelSeparation") is not None:
            layout_obj.set_separation(hier["levelSeparation"])
        if hier.get("treeSpacing") is not None:
            layout_obj.set_tree_spacing(hier["treeSpacing"])
        if hier.get("edgeMinimization") is not None:
            layout_obj.set_edge_minimization(hier["edgeMinimization"])

        handled = {"levelSeparation", "treeSpacing", "edgeMinimization"}
        for attr, value in hier.items():
            if attr in handled or value is None:
                continue
            setattr(layout_obj.hierarchical, attr, value)


def set_options(config):
    """
    Create and configure a pyvis Options object using the provided config.
    Delegates to helper functions for each sub-object (physics, edges, layout, interaction, configure).
    Returns:
        Options: Fully configured pyvis Options object.
    """
    options = Options(layout=config.get("layout") is not None)
    if config.get("physics"):
        set_physics_options(options.physics, config.physics)
    if config.get("edges"):
        set_edge_options(options.edges, config.edges)
    if config.get("layout"):
        set_layout_options(options.layout, config.layout)

    for obj in ["interaction", "configure"]:
        if config.get(obj):
            for attr, value in getattr(config, obj).items():
                if value is not None:
                    setattr(getattr(options, obj), attr, value)

    return options


# --- Graph construction utilities ---


def get_edge_kwargs(entry, config, operation, block={}):
    """
    Merge edge styling options from config and YAML overrides for a given relationship entry.

    Args:
        entry (dict): Relationship entry from YAML.
        config (Config): Configuration object.
        operation (str): Relationship type (series, parallel, convergence, divergence).
        block (dict): Optional block-level overrides.
    Returns:
        dict: Edge keyword arguments for pyvis.
    """
    edge_kwargs = config.edge.copy() if hasattr(config, "edge") else {}
    edge_kwargs["color"] = (
        entry["color"]
        if "color" in entry
        else block.get("color") or config.operation.get(operation, {}).get("color")
    )
    edge_kwargs["smooth"] = (
        entry["smooth"]
        if "smooth" in entry
        else block.get("smooth")
        or config.operation.get(operation, {}).get("smooth", False)
    )
    edge_kwargs["title"] = (
        entry["title"] if "title" in entry else block.get("title", operation)
    )
    return edge_kwargs


def add_linear_edges(data, config, net, operation):
    """
    Add edges for 'series' or 'parallel' relationships.

    Args:
        data: Section data (series or parallel).
        config (Config): Configuration object.
        net (Network): pyvis Network object.
        operation (str): 'series' or 'parallel'.
    """
    if isinstance(data, dict) and "items" in data:
        data = data["items"]

    for entry in data:
        edge_kwargs = get_edge_kwargs(entry=entry, config=config, operation=operation)
        edge_kwargs["arrows"] = "none" if operation == "parallel" else "to"
        if isinstance(entry, dict) and "items" in entry:
            items = entry["items"]
            if isinstance(items, list) and all(isinstance(sub, list) for sub in items):
                for sublist in items:
                    for i in range(len(sublist) - 1):
                        net.add_edge(sublist[i], sublist[i + 1], **edge_kwargs)
            else:
                for i in range(len(items) - 1):
                    net.add_edge(items[i], items[i + 1], **edge_kwargs)
        else:
            items = entry
            for i in range(len(items) - 1):
                net.add_edge(items[i], items[i + 1], **edge_kwargs)


def add_branching_edges(data, config, net, operation):
    """
    Add edges for 'convergence' or 'divergence' relationships.

    Args:
        data: Section data (convergence or divergence).
        config (Config): Configuration object.
        net (Network): pyvis Network object.
        operation (str): 'convergence' or 'divergence'.
    """
    if operation == "convergence":
        from_key = "materials"
        to_key = "product"
        to_many = False
    elif operation == "divergence":
        from_key = "root"
        to_key = "branches"
        to_many = True
    else:
        raise ValueError(f"Unknown operation: {operation}")

    def add_entry(entry, block=None):
        if not isinstance(entry, dict):
            return
        from_vals = entry.get(from_key, [])
        to_val = entry.get(to_key)
        edge_kwargs = get_edge_kwargs(
            entry=entry, config=config, operation=operation, block=block or {}
        )
        if to_many:
            if not from_vals:
                return
            for target in to_val or []:
                net.add_edge(from_vals, target, **edge_kwargs)
        else:
            for source in from_vals:
                net.add_edge(source, to_val, **edge_kwargs)

    flat_entries = []
    if isinstance(data, list):
        for block in data:
            block_items = (
                block.get("items")
                if isinstance(block, dict) and "items" in block
                else None
            )
            if block_items:
                for entry in block_items:
                    add_entry(entry, block)
            else:
                flat_entries.append(block)
    elif isinstance(data, dict) and "items" in data:
        for entry in data["items"]:
            add_entry(entry)
    else:
        flat_entries = data

    for entry in flat_entries:
        add_entry(entry)


def collect_items_from_block(block, section):

    def flatten_items(items):
        """
        Recursively flatten nested lists and strings to yield all card names.
        """
        if isinstance(items, str):
            yield items
        elif isinstance(items, list):
            for el in items:
                yield from flatten_items(el)
        elif items is not None:
            yield items

    items_set = set()
    # Collect all card names for node creation based on section type
    if section in ["series", "parallel"]:
        if isinstance(block, dict) and "items" in block:
            items = block["items"]
            items_set.update(flatten_items(items))
        else:
            items_set.update(flatten_items(block))
    elif section == "convergence":
        if isinstance(block, dict) and "items" in block:
            for entry in block["items"]:
                items_set.update(flatten_items(entry.get("materials", [])))
                product = entry.get("product")
                if product:
                    items_set.add(product)
        else:
            items_set.update(flatten_items(block.get("materials", [])))
            product = block.get("product")
            if product:
                items_set.add(product)
    elif section == "divergence":
        if isinstance(block, dict) and "items" in block:
            for entry in block["items"]:
                root = entry.get("root")
                if root:
                    items_set.add(root)
                items_set.update(flatten_items(entry.get("branches", [])))
        else:
            root = block.get("root") if isinstance(block, dict) else None
            if root:
                items_set.add(root)
            branches = block.get("branches", []) if isinstance(block, dict) else []
            items_set.update(flatten_items(branches))
    return items_set


# --- Main network construction function ---


def build_network(yaml_path):
    """
    Build an interactive relationship network from a YAML file.
    Loads configuration, downloads images, adds nodes and edges, applies all options, and scales node sizes.

    Args:
        yaml_path (str): Path to the YAML configuration file.
    Returns:
        Network: Configured pyvis Network object.
    """
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)

    # Load and merge config overrides
    raw_config = data.get("config", {})
    if isinstance(raw_config, list):
        merged_config = {}
        for entry in raw_config:
            if isinstance(entry, dict):
                merged_config.update(entry)
        raw_config = merged_config
    config = Config(raw_config)

    all_items = set()
    for section in ["series", "parallel", "convergence", "divergence"]:
        for block in data.get(section, []):
            all_items.update(collect_items_from_block(block, section))

    net = Network(**config.network)
    net.options = set_options(config)

    if config.get("download_images", True):
        download_images(all_items, config)

    node_kwargs = config.node.copy() if hasattr(config, "node") else {}
    node_scale = node_kwargs.pop(
        "scale", None
    )  # Remove scaling options from node kwargs
    node_scale_factor = node_kwargs.pop("scale_factor", None)
    for item in sorted(all_items):
        node_kwargs["title"] = item
        node_kwargs["image"] = f"images/{image_filename(item)}.jpg"
        net.add_node(item, **node_kwargs)

    for operation in ["series", "parallel"]:
        add_linear_edges(data.get(operation, []), config, net, operation)
    for operation in ["convergence", "divergence"]:
        add_branching_edges(
            data.get(operation, []),
            config,
            net,
            operation=operation,
        )

    # --- Post-processing: scale node size by degree ---
    if node_scale:
        adj_list = net.get_adj_list()
        node_degrees = []
        for node in net.nodes:
            node_id = node["id"]
            base_size = node["size"]
            degree = len(adj_list.get(node_id, []))
            scale_factor = node_scale_factor
            node["size"] = base_size + scale_factor * degree
            node_degrees.append((str(node_id), degree))

        # Print table header
        col1 = "Node"
        col2 = "Edges"
        width1 = max(len(col1), max(len(n) for n, _ in node_degrees))
        width2 = max(len(col2), max(len(str(d)) for _, d in node_degrees))
        print(f"\n{col1:<{width1}} | {col2:<{width2}}")
        print(f"{'-'*width1}-+-{'-'*width2}")
        for n, d in node_degrees:
            print(f"{n:<{width1}} | {d+1:<{width2}}")

    if config.buttons.show:
        net.show_buttons(filter_=config.buttons.filter)

    return net


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build an interactive relationship network from a YAML file using pyvis."
    )
    parser.add_argument(
        "yaml_file",
        default="network.yaml",
        nargs="?",
        help="Path to the network YAML file.",
    )
    args = parser.parse_args()
    net = build_network(args.yaml_file)

    base_name = os.path.splitext(os.path.basename(args.yaml_file))[0]
    html_output = os.path.abspath(f"{base_name}.html")
    net.write_html(html_output)
    print("Network saved to:", html_output)

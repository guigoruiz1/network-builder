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


class Config:
    default = {
        "node": {
            "scale": False,
            "scale_factor": 10,
            "shape": "image",
            "size": 100,
            "borderWidthSelected": 4,
            "shapeProperties": {"useBorderWithImage": True},
        },
        "edge": {"arrowStrikethrough": False, "width": 20},
        "operation": {
            "series": {"edge": {"color": "orange", "smooth": True}},
            "convergence": {"edge": {"color": "purple", "smooth": True}},
            "parallel": {"edge": {"color": "green", "smooth": False}},
            "divergence": {"edge": {"color": "red", "smooth": True}},
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
            "directed": False,
            "select_menu": True,
        },
        "download_images": False,
    }

    @staticmethod
    def deep_merge_dicts(a, b):
        result = dict(a)
        for k, v in b.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = Config.deep_merge_dicts(result[k], v)
            else:
                result[k] = v
        return result

    @classmethod
    def load(cls, config):

        if isinstance(config, list):
            merged_config = {}
            for entry in config:
                if isinstance(entry, dict):
                    merged_config.update(entry)
            config = merged_config
        return cls.deep_merge_dicts(cls.default, config)


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
    # Use dictionary-style access for sub-objects
    if config.get("physics"):
        set_physics_options(options["physics"], config["physics"])
    if config.get("edges"):
        set_edge_options(options["edges"], config["edges"])
    if config.get("layout"):
        set_layout_options(options["layout"], config["layout"])

    for obj in ["interaction", "configure"]:
        val = config.get(obj)
        if val:
            for attr, value in val.items():
                if value is not None:
                    setattr(getattr(options, obj), attr, value)

    return options


# --- Graph construction utilities ---


def get_kwargs(entry_style, config, operation, block_style={}, config_key="edge"):
    """
    Merge styling options from config and YAML overrides for a given relationship entry.

    Args:
        entry_style (dict): Entry level style overrides.
        config (dict): Configuration dictionary.
        operation (str): Relationship type (series, parallel, convergence, divergence).
        block_style (dict): Optional block-level style overrides.
        config_key (str): Which config key to use ('edge' or 'node').
    Returns:
        dict: Keyword arguments for pyvis.
    """
    base = config.get(config_key, {})
    op = config.get("operation", {}).get(operation, {}) if operation else {}
    op = op.get(config_key, {})
    merged = Config.deep_merge_dicts(base, op)
    merged = Config.deep_merge_dicts(merged, block_style)
    merged = Config.deep_merge_dicts(merged, entry_style)
    return merged


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
        # Extract edge style from entry['edge'] if present, else empty dict
        style = entry.get("edge", {}) if isinstance(entry, dict) else {}
        edge_kwargs = get_kwargs(
            entry_style=style,
            config=config,
            operation=operation,
            config_key="edge",
        )
        # Handle title separately
        edge_kwargs["title"] = (
            entry.get("title") if isinstance(entry, dict) else operation
        )
        if "arrows" not in edge_kwargs:
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

    def add_entry(entry, block={}):
        if not isinstance(entry, dict):
            return
        from_vals = entry.get(from_key, [])
        to_val = entry.get(to_key)
        # Extract edge style from entry['edge'] if present, else empty dict
        style = entry.get("edge", {})
        # Extract block style from block['edge'] if present, else empty dict
        block_style = block.get("edge", {})
        # Handle title separately
        edge_kwargs = get_kwargs(
            entry_style=style,
            config=config,
            operation=operation,
            block_style=block_style,
            config_key="edge",
        )
        edge_kwargs["title"] = entry.get("title", block.get("title", operation))
        if "arrows" not in edge_kwargs:
            edge_kwargs["arrows"] = "to"

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


def get_nodes(
    data, operations=["series", "parallel", "convergence", "divergence"], config={}
):
    """
    Collect all unique node names from the YAML data across all relationship sections.
    Merges any node-specific kwargs from the blocks and entries, including block-level and entry-level node styles.

    Args:
        data: The entire YAML data dictionary.
        operations: List of operation sections to process.
        config: The loaded config dict (for merging global/operation-level node config).
    Returns:
        dict: Mapping of node names to their merged kwargs.
    """

    def flatten_items(items):
        if isinstance(items, str):
            yield items
        elif isinstance(items, list):
            for el in items:
                yield from flatten_items(el)
        elif items is not None:
            yield items

    node_info = {}
    global_node_kwargs = data.get("config", {}).get("node", {})

    def add_node(name, entry_style, block_style, section):
        # Merge: global node config < operation-level < block-level < entry-level
        node_kwargs = get_kwargs(
            entry_style=entry_style,
            config=config,
            operation=section,
            block_style=block_style,
            config_key="node",
        )
        node_kwargs = Config.deep_merge_dicts(global_node_kwargs, node_kwargs)
        if name not in node_info:
            node_info[name] = node_kwargs
        else:
            node_info[name] = Config.deep_merge_dicts(node_info[name], node_kwargs)

    for section in operations:
        for block in data.get(section, []):
            block_node_style = block.get("node", {}) if isinstance(block, dict) else {}
            if section in ["series", "parallel"]:
                if isinstance(block, dict) and "items" in block:
                    items = block["items"]
                    for name in flatten_items(items):
                        add_node(name, {}, block_node_style, section)
                else:
                    for name in flatten_items(block):
                        add_node(name, {}, block_node_style, section)
            elif section == "convergence":
                if isinstance(block, dict) and "items" in block:
                    for entry in block["items"]:
                        entry_node_style = entry.get("node", {})
                        for name in flatten_items(entry.get("materials", [])):
                            add_node(name, entry_node_style, block_node_style, section)
                        product = entry.get("product")
                        if product:
                            add_node(
                                product, entry_node_style, block_node_style, section
                            )
                else:
                    for name in flatten_items(block.get("materials", [])):
                        add_node(name, {}, block_node_style, section)
                    product = block.get("product") if isinstance(block, dict) else None
                    if product:
                        add_node(product, {}, block_node_style, section)
            elif section == "divergence":
                if isinstance(block, dict) and "items" in block:
                    for entry in block["items"]:
                        entry_node_style = entry.get("node", {})
                        root = entry.get("root")
                        if root:
                            add_node(root, entry_node_style, block_node_style, section)
                        for name in flatten_items(entry.get("branches", [])):
                            add_node(name, entry_node_style, block_node_style, section)
                else:
                    root = block.get("root") if isinstance(block, dict) else None
                    if root:
                        add_node(root, {}, block_node_style, section)
                    branches = (
                        block.get("branches", []) if isinstance(block, dict) else []
                    )
                    for name in flatten_items(branches):
                        add_node(name, {}, block_node_style, section)

    return node_info


def scale_nodes(net, scale_factor=10, print_table=False):
    adj_list = net.get_adj_list()
    node_degrees = []
    for node in net.nodes:
        node_id = node["id"]
        base_size = node["size"]
        degree = len(adj_list.get(node_id, []))
        node["size"] = base_size + scale_factor * degree
        node_degrees.append((str(node_id), degree))

    # Print table header
    if print_table:
        col1 = "Node"
        col2 = "Edges"
        width1 = max(len(col1), max(len(n) for n, _ in node_degrees))
        width2 = max(len(col2), max(len(str(d)) for _, d in node_degrees))
        print(f"\n{col1:<{width1}} | {col2:<{width2}}")
        print(f"{'-'*width1}-+-{'-'*width2}")
        for n, d in node_degrees:
            print(f"{n:<{width1}} | {d:<{width2}}")


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

    config = Config.load(config=data.get("config", {}))

    node_info = get_nodes(
        data=data,
        operations=["series", "parallel", "convergence", "divergence"],
        config=config,
    )

    net = Network(**config["network"])
    net.options = set_options(config=config)

    if config.get("download_images", True):
        download_images(names=node_info.keys(), config=config)

    global_node_kwargs = config["node"].copy()
    node_scale = global_node_kwargs.pop("scale", None)
    node_scale_factor = global_node_kwargs.pop("scale_factor", None)
    node_print_table = global_node_kwargs.pop("print_table", False)

    for item in sorted(node_info.keys()):
        node_info[item]["title"] = item
        node_info[item]["image"] = f"images/{image_filename(item)}.jpg"
        net.add_node(item, **node_info[item])

    for operation in ["series", "parallel"]:
        add_linear_edges(
            data=data.get(operation, []), config=config, net=net, operation=operation
        )
    for operation in ["convergence", "divergence"]:
        add_branching_edges(
            data=data.get(operation, []),
            config=config,
            net=net,
            operation=operation,
        )

    # --- Post-processing: scale node size by degree ---
    if node_scale:
        scale_nodes(net, scale_factor=node_scale_factor, print_table=node_print_table)

    if config["buttons"]["show"]:
        net.show_buttons(filter_=config["buttons"]["filter"])

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

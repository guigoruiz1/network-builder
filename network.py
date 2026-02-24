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
    """
    Dictionary subclass that allows attribute-style access to keys, recursively.
    Useful for deep config objects.
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
    """

    def __init__(self, overrides=None):
        defaults = {
            "colors": {
                "series": "orange",
                "convergence": "purple",
                "parallel": "green",
                "divergence": "red",
            },
            "node": {
                "shape": "image",
                "size": 100,
                "borderWidthSelected": 4,
                "shapeProperties": {"useBorderWithImage": True},
            },
            "edge": {
                "arrowStrikethrough": False,
                "arrowScaleFactor": 2,
                "width": 4,
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
                    "damping": 0.09,
                },
            },
            "network": {
                "height": "90vh",
                "width": "100%",
                "directed": True,
                "select_menu": True,
            },
            "download_images": True,  # Toggle downloading card images
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
    """
    Sanitize card name for filenames (remove all non-alphanumeric characters).
    Args:
        name (str): The card name to sanitize.
    Returns:
        str: Sanitized string suitable for filenames.
    """
    return re.sub(r"[^a-zA-Z0-9]", "", name)


def _download_card_images_fallback(card_names, config):
    """
    Fallback method to download and crop card images directly from Yugipedia API.
    Used when yugiquery utilities are unavailable. Saves images to `images/<Card_Name>.jpg`.
    Existing files are skipped.
    Args:
        card_names (Iterable[str]): Card names to download.
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
    """
    Crop a PIL image to the configured section and optionally resize.
    Args:
        im (PIL.Image): The image to crop.
        config (Config): Configuration object with crop parameters.
        out_size (tuple or None): Optional output size (width, height).
    Returns:
        PIL.Image: Cropped (and possibly resized) image.
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


def download_card_images(card_names, config):
    """
    Download and crop card images from Yugipedia.
    Attempts yugiquery utilities first (async + featured images), falls back to direct API.
    Saves to `images/<Card_Name>.jpg`. Skips existing files.
    Args:
        card_names (Iterable[str]): Card names to download.
        config (Config): Configuration object for cropping.
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


def add_node(name, config, net):
    """
    Add a node to the network graph with its image.
    Args:
        name (str): Card name.
        config (Config): Configuration object.
        net (Network): pyvis Network object.
    """
    if name not in nodes:
        nodes.add(name)
        node_kwargs = config.node.copy() if hasattr(config, "node") else {}
        node_kwargs["title"] = name
        node_kwargs["image"] = f"images/{sanitize_card_name(name)}.jpg"
        net.add_node(name, **node_kwargs)


def add_edge(src, dst, operation, edge_kwargs, net):
    """
    Add a styled edge between nodes based on operation type, using edge_kwargs for all options.
    Args:
        src (str): Source node name.
        dst (str): Destination node name.
        operation (str): One of "series", "convergence", "parallel", "divergence".
        edge_kwargs (dict): All edge options (merged from config.edge and YAML overrides).
        net (Network): pyvis Network object.
    """
    # Always set these
    edge_kwargs = edge_kwargs.copy()  # Defensive copy
    edge_kwargs["arrows"] = "none" if operation == "parallel" else "to"
    edge_kwargs["smooth"] = operation != "parallel"
    if "title" not in edge_kwargs or not edge_kwargs["title"]:
        edge_kwargs["title"] = operation
    net.add_edge(src, dst, **edge_kwargs)


def set_physics_options(physics_obj, config):
    """
    Apply physics-related configuration to the pyvis Physics object.
    Supports enabling/disabling physics, selecting solvers, and toggling stabilization.
    """
    physics_obj.enabled = config.get("enabled", True)
    # Set physics solvers if present in config
    if config.get("repulsion"):
        physics_obj.use_repulsion(config.repulsion)
    if config.get("forceAtlas2Based"):
        physics_obj.use_force_atlas_2based(config.forceAtlas2Based)
    if config.get("barnesHut"):
        physics_obj.use_barnes_hut(config.barnesHut)
    if config.get("hierarchicalRepulsion"):
        physics_obj.use_hrepulsion(config.hierarchicalRepulsion)
    # Toggle stabilization if specified (expects a boolean)
    if config.get("stabilization") is not None:
        physics_obj.toggle_stabilization(bool(config.stabilization))


def set_edge_options(edges_obj, config):
    """
    Apply edge-related configuration to the pyvis EdgeOptions object.
    Supports toggling smoothness type and color inheritance.
    """
    if config.get("smooth_type"):
        edges_obj.toggle_smoothness(config.smooth_type)
    if config.get("inherit_colors") is not None:
        edges_obj.inherit_colors(config.inherit_colors)


def set_layout_options(layout_obj, config):
    """
    Apply layout-related configuration to the pyvis Layout object.
    Supports random seed, improved layout, and hierarchical layout options.
    """
    if config.get("randomSeed") is not None:
        layout_obj.randomSeed = config.randomSeed
    if config.get("improvedLayout") is not None:
        layout_obj.improvedLayout = config.improvedLayout
    # Hierarchical layout options
    if config.get("hierarchical"):
        hier = config.hierarchical
        if hier.get("enabled") is not None:
            layout_obj.hierarchical.enabled = hier.enabled
        if hier.get("levelSeparation") is not None:
            layout_obj.set_separation(hier.levelSeparation)
        if hier.get("treeSpacing") is not None:
            layout_obj.set_tree_spacing(hier.treeSpacing)
        if hier.get("edgeMinimization") is not None:
            layout_obj.set_edge_minimization(hier.edgeMinimization)
        if hier.get("blockShifting") is not None:
            layout_obj.hierarchical.blockShifting = hier.blockShifting
        if hier.get("parentCentralization") is not None:
            layout_obj.hierarchical.parentCentralization = hier.parentCentralization
        if hier.get("sortMethod") is not None:
            layout_obj.hierarchical.sortMethod = hier.sortMethod


def set_interaction_options(interaction_obj, config):
    """
    Apply interaction-related configuration to the pyvis Interaction object.
    Supports toggling drag and hide options for nodes and edges.
    """
    if config.get("hideEdgesOnDrag") is not None:
        interaction_obj.hideEdgesOnDrag = config.hideEdgesOnDrag
    if config.get("hideNodesOnDrag") is not None:
        interaction_obj.hideNodesOnDrag = config.hideNodesOnDrag
    if config.get("dragNodes") is not None:
        interaction_obj.dragNodes = config.dragNodes


def set_configure_options(configure_obj, config):
    """
    Apply configure-related configuration to the pyvis Configure object.
    Supports enabling the option editor and setting filters.
    """
    if config.get("enabled") is not None:
        configure_obj.enabled = config.enabled
    if config.get("filter") is not None:
        configure_obj.filter = config.filter


def set_options(config):
    """
    Create and configure a pyvis Options object using the provided config.
    Delegates to helper functions for each sub-object (physics, edges, layout, interaction, configure).
    Returns:
        options (Options): A fully configured pyvis Options object.
    """
    options = Options()
    if config.get("physics"):
        set_physics_options(options.physics, config.physics)
    if config.get("edges"):
        set_edge_options(options.edges, config.edges)
    if config.get("layout"):
        set_layout_options(options.layout, config.layout)
    if config.get("interaction"):
        set_interaction_options(options.interaction, config.interaction)
    if config.get("configure"):
        set_configure_options(options.configure, config.configure)
    return options


def build_graph(yaml_path):
    """
    Build an interactive card relationship graph from a YAML file.
    Loads configuration, downloads images, adds nodes and edges, and applies all options.
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

    # Collect all unique item names from all sections (flatten lists)
    all_items = set()

    def flatten_items(items):
        if isinstance(items, str):
            yield items
        elif isinstance(items, list):
            for el in items:
                yield from flatten_items(el)
        elif items is not None:
            yield items

    # Collect items from all sections
    for section, key in [("series", "items"), ("parallel", "items")]:
        for entry in data.get(section, []):
            items = entry.get(key, []) if isinstance(entry, dict) else entry
            all_items.update(flatten_items(items))

    for entry in data.get("convergence", []):
        all_items.update(flatten_items(entry.get("materials", [])))
        product = entry.get("product")
        if product:
            all_items.add(product)

    for entry in data.get("divergence", []):
        root = entry.get("root")
        if root:
            all_items.add(root)
        all_items.update(flatten_items(entry.get("branches", [])))

    # Create the pyvis Network object
    net = Network(**config.network)

    for item in sorted(all_items):
        add_node(item, config, net)  # Add to nodes set for image downloading

    # Download images if enabled in config
    if config.get("download_images", True):
        download_card_images(all_items, config)

    # --- SERIES ---
    series_data = data.get("series", [])
    if isinstance(series_data, dict) and "items" in series_data:
        series_data = series_data["items"]
    for entry in series_data:
        if isinstance(entry, dict) and "items" in entry:
            edge_kwargs = config.edge.copy() if hasattr(config, "edge") else {}
            if "color" in entry:
                edge_kwargs["color"] = entry["color"]
            else:
                edge_kwargs["color"] = config.colors["series"]
            if "title" in entry:
                edge_kwargs["title"] = entry["title"]
            items = entry["items"]
            # items can be a list of lists or a flat list
            if isinstance(items, list) and all(isinstance(sub, list) for sub in items):
                for sublist in items:
                    for node in sublist:
                        add_node(node, config, net)
                    for i in range(len(sublist) - 1):
                        add_edge(sublist[i], sublist[i + 1], "series", edge_kwargs, net)
            else:
                for node in items:
                    add_node(node, config, net)
                for i in range(len(items) - 1):
                    add_edge(items[i], items[i + 1], "series", edge_kwargs, net)
        else:
            items = entry
            edge_kwargs = config.edge.copy() if hasattr(config, "edge") else {}
            edge_kwargs["color"] = config.colors["series"]
            for node in items:
                add_node(node, config, net)
            for i in range(len(items) - 1):
                add_edge(items[i], items[i + 1], "series", edge_kwargs, net)

    # --- PARALLEL ---
    parallel_data = data.get("parallel", [])
    if isinstance(parallel_data, dict) and "items" in parallel_data:
        parallel_data = parallel_data["items"]
    for entry in parallel_data:
        if isinstance(entry, dict) and "items" in entry:
            edge_kwargs = config.edge.copy() if hasattr(config, "edge") else {}
            if "color" in entry:
                edge_kwargs["color"] = entry["color"]
            else:
                edge_kwargs["color"] = config.colors["parallel"]
            if "title" in entry:
                edge_kwargs["title"] = entry["title"]
            items = entry["items"]
            if isinstance(items, list) and all(isinstance(sub, list) for sub in items):
                for sublist in items:
                    for node in sublist:
                        add_node(node, config, net)
                    for i in range(len(sublist) - 1):
                        add_edge(
                            sublist[i], sublist[i + 1], "parallel", edge_kwargs, net
                        )
            else:
                for node in items:
                    add_node(node, config, net)
                for i in range(len(items) - 1):
                    add_edge(items[i], items[i + 1], "parallel", edge_kwargs, net)
        else:
            items = entry
            edge_kwargs = config.edge.copy() if hasattr(config, "edge") else {}
            edge_kwargs["color"] = config.colors["parallel"]
            for node in items:
                add_node(node, config, net)
            for i in range(len(items) - 1):
                add_edge(items[i], items[i + 1], "parallel", edge_kwargs, net)

    # --- CONVERGENCE ---
    convergence_data = data.get("convergence", [])
    block_entries = []
    flat_entries = []
    if isinstance(convergence_data, list):
        for block in convergence_data:
            block_title = block.get("title") if isinstance(block, dict) else None
            block_items = (
                block.get("items")
                if isinstance(block, dict) and "items" in block
                else None
            )
            if block_items:
                for entry in block_items:
                    entry_title = (
                        entry.get("title") if isinstance(entry, dict) else None
                    )
                    materials = (
                        entry.get("materials", []) if isinstance(entry, dict) else []
                    )
                    product = entry.get("product") if isinstance(entry, dict) else None
                    edge_kwargs = config.edge.copy() if hasattr(config, "edge") else {}
                    edge_kwargs["color"] = entry.get(
                        "color", config.colors["convergence"]
                    )
                    edge_kwargs["title"] = entry_title or block_title
                    for mat in materials:
                        add_node(mat, config, net)
                    add_node(product, config, net)
                    for mat in materials:
                        add_edge(mat, product, "convergence", edge_kwargs, net)
            else:
                flat_entries.append(block)
    elif isinstance(convergence_data, dict) and "items" in convergence_data:
        block_title = convergence_data.get("title")
        for entry in convergence_data["items"]:
            entry_title = entry.get("title") if isinstance(entry, dict) else None
            materials = entry.get("materials", []) if isinstance(entry, dict) else []
            product = entry.get("product") if isinstance(entry, dict) else None
            edge_kwargs = config.edge.copy() if hasattr(config, "edge") else {}
            edge_kwargs["color"] = entry.get("color", config.colors["convergence"])
            edge_kwargs["title"] = entry_title or block_title
            for mat in materials:
                add_node(mat, config, net)
            add_node(product, config, net)
            for mat in materials:
                add_edge(mat, product, "convergence", edge_kwargs, net)
    else:
        flat_entries = convergence_data
    for entry in flat_entries:
        materials = entry.get("materials", []) if isinstance(entry, dict) else []
        product = entry.get("product") if isinstance(entry, dict) else None
        edge_kwargs = config.edge.copy() if hasattr(config, "edge") else {}
        edge_kwargs["color"] = entry.get("color", config.colors["convergence"])
        edge_kwargs["title"] = entry.get("title")
        for mat in materials:
            add_node(mat, config, net)
        add_node(product, config, net)
        for mat in materials:
            add_edge(mat, product, "convergence", edge_kwargs, net)

    # --- DIVERGENCE ---
    divergence_data = data.get("divergence", [])
    block_entries = []
    flat_entries = []
    if isinstance(divergence_data, list):
        for block in divergence_data:
            block_title = block.get("title") if isinstance(block, dict) else None
            block_items = (
                block.get("items")
                if isinstance(block, dict) and "items" in block
                else None
            )
            if block_items:
                for entry in block_items:
                    entry_title = (
                        entry.get("title") if isinstance(entry, dict) else None
                    )
                    root = entry.get("root") if isinstance(entry, dict) else None
                    branches = (
                        entry.get("branches", []) if isinstance(entry, dict) else []
                    )
                    edge_kwargs = config.edge.copy() if hasattr(config, "edge") else {}
                    edge_kwargs["color"] = entry.get(
                        "color", config.colors["divergence"]
                    )
                    edge_kwargs["title"] = entry_title or block_title
                    if not root:
                        continue
                    add_node(root, config, net)
                    for branch in branches:
                        add_node(branch, config, net)
                        add_edge(root, branch, "divergence", edge_kwargs, net)
            else:
                flat_entries.append(block)
    elif isinstance(divergence_data, dict) and "items" in divergence_data:
        block_title = divergence_data.get("title")
        for entry in divergence_data["items"]:
            entry_title = entry.get("title") if isinstance(entry, dict) else None
            root = entry.get("root") if isinstance(entry, dict) else None
            branches = entry.get("branches", []) if isinstance(entry, dict) else []
            edge_kwargs = config.edge.copy() if hasattr(config, "edge") else {}
            edge_kwargs["color"] = entry.get("color", config.colors["divergence"])
            edge_kwargs["title"] = entry_title or block_title
            if not root:
                continue
            add_node(root, config, net)
            for branch in branches:
                add_node(branch, config, net)
                add_edge(root, branch, "divergence", edge_kwargs, net)
    else:
        flat_entries = divergence_data
    for entry in flat_entries:
        root = entry.get("root") if isinstance(entry, dict) else None
        branches = entry.get("branches", []) if isinstance(entry, dict) else []
        edge_kwargs = config.edge.copy() if hasattr(config, "edge") else {}
        edge_kwargs["color"] = entry.get("color", config.colors["divergence"])
        edge_kwargs["title"] = entry.get("title")
        if not root:
            continue
        add_node(root, config, net)
        for branch in branches:
            add_node(branch, config, net)
            add_edge(root, branch, "divergence", edge_kwargs, net)

    # Apply all options from config
    net.options = set_options(config)

    # Show interactive buttons if enabled
    if config.buttons.show:
        net.show_buttons(filter_=config.buttons.filter)

    return net


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build an interactive card relationship graph from a YAML file."
    )
    parser.add_argument(
        "yaml_file",
        default="network.yaml",
        nargs="?",
        help="Path to the network YAML file.",
    )
    args = parser.parse_args()
    net = build_graph(args.yaml_file)

    base_name = os.path.splitext(os.path.basename(args.yaml_file))[0]
    html_output = os.path.abspath(f"{base_name}.html")
    net.write_html(html_output)
    print("Saved to:", html_output)

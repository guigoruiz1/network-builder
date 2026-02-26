# --- Imports ---

import yaml
import os
import argparse
from pyvis.options import Options
from pyvis.network import Network
from collections import Counter

# --- Global Configuration ---


class Config:
    default = {
        "node": {
            "scale_factor": 0,
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

    def __init__(self, config=None):
        if config is None:
            config = {}
        if isinstance(config, list):
            merged_config = {}
            for entry in config:
                if isinstance(entry, dict):
                    merged_config.update(entry)
            config = merged_config
        self._data = Config.deep_merge_dicts(Config.default, config)

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        value = self._data.get(key, default)
        if value is None:
            return {}
        return value

    def __contains__(self, key):
        return key in self._data

    def __repr__(self):
        return f"Config({self._data!r})"


config = Config()  # Global config variable

# --- Option Configuration Utilities ---


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


def set_options():
    """
    Create and configure a pyvis Options object using the global config.
    Delegates to helper functions for each sub-object (physics, edges, layout, interaction, configure).
    Returns:
        Options: Fully configured pyvis Options object.
    """
    global config

    options = Options(layout=bool(config.get("layout")))
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


# --- General Graph Utilities ---


def flatten_items(items):
    if isinstance(items, str):
        yield items
    elif isinstance(items, list):
        for el in items:
            yield from flatten_items(el)
    elif items is not None:
        yield items


def section_has_branching(data):
    """
    Recursively checks if any entry in the provided data (dict or list) contains both 'from' and 'to' keys.
    This identifies branching relationships in a YAML structure, regardless of nesting.

    Args:
        data: The section data (dict or list) to check for branching relationships.
    Returns:
        bool: True if any entry is a branching relationship, False otherwise.
    """
    stack = [data]
    while stack:
        entry = stack.pop()
        if isinstance(entry, dict):
            if "from" in entry and "to" in entry:
                return True
            if "items" in entry and isinstance(entry["items"], list):
                stack.extend(entry["items"])
        elif isinstance(entry, list):
            stack.extend(entry)
    return False


def get_kwargs(entry_style, operation, block_style={}, config_key="edge"):
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
    global config
    base = config.get(config_key)
    op = config.get("operation")
    op = op.get(operation, {}) if operation else {}
    op = op.get(config_key, {})
    merged = Config.deep_merge_dicts(base, op)
    merged = Config.deep_merge_dicts(merged, block_style)
    merged = Config.deep_merge_dicts(merged, entry_style)
    return merged


# --- Node Collection and Editing ---


def get_nodes(data):
    """
    Collect all unique node names from the YAML data across all relationship operations.
    Merges any node-specific kwargs from the blocks and entries, including block-level and entry-level node styles.

    Args:
        data: The YAML data dictionary containing operations and node information.
    Returns:
        dict: Mapping of node names to their merged kwargs.
    """

    node_info = {}
    global_node_kwargs = data.get("config", {}).get("node", {}) or {}

    def add_node(name, entry_style, block_style, section):
        # Merge: global node config < operation-level < block-level < entry-level
        node_kwargs = get_kwargs(
            entry_style=entry_style,
            operation=section,
            block_style=block_style,
            config_key="node",
        )
        node_kwargs = Config.deep_merge_dicts(global_node_kwargs, node_kwargs)
        if name not in node_info:
            node_info[name] = node_kwargs
        else:
            node_info[name] = Config.deep_merge_dicts(node_info[name], node_kwargs)

    for section in data:
        for block in data[section]:
            block_node_style = block.get("node", {}) if isinstance(block, dict) else {}
            # If block has 'items', iterate entries; else treat block as entry
            entries = (
                block["items"]
                if isinstance(block, dict) and "items" in block
                else [block]
            )
            for entry in entries:
                entry_node_style = (
                    entry.get("node", {}) if isinstance(entry, dict) else {}
                )
                # If entry is a dict with 'from' or 'to', treat as branching; else treat as linear list
                if isinstance(entry, dict) and ("from" in entry or "to" in entry):
                    from_vals = entry.get("from", [])
                    to_vals = entry.get("to", [])
                    for name in flatten_items(from_vals):
                        add_node(name, entry_node_style, block_node_style, section)
                    for name in flatten_items(to_vals):
                        add_node(name, entry_node_style, block_node_style, section)
                else:
                    # Treat as a list of node names (linear)
                    for name in flatten_items(entry):
                        add_node(name, entry_node_style, block_node_style, section)

    return node_info


def edit_nodes(net, scale_factor=None, recolor=False, print_table=False):
    """
    Edit node properties in a pyvis Network object.
    Optionally scale node size by degree, recolor nodes by edge color majority, and print a summary table.

    Args:
        net (Network): pyvis Network object.
        scale_factor (float, optional): If set, increases node size by (scale_factor * degree).
        recolor (bool, optional): If True, recolors node to the most common color among its edges.
        print_table (bool, optional): If True, prints a table of node degrees and new colors.
    """
    node_stats = []
    for node in net.nodes:
        node_id = node["id"]
        degree = len(net.neighbors(node_id))
        color = node["color"]
        if scale_factor:
            base_size = node.get("size", 0)
            node["size"] = base_size + scale_factor * degree
        if recolor:
            connected_edges = [
                e for e in net.edges if e["from"] == node_id or e["to"] == node_id
            ]
            colors = [e.get("color") for e in connected_edges if e.get("color")]
            if colors:
                most_common_color, _ = Counter(colors).most_common(1)[0]
                node["color"] = most_common_color
                color = most_common_color
        node_stats.append(
            {
                "id": node_id,
                "degree": degree,
                "color": color,
            }
        )

    if print_table:
        # Always print all nodes, even if some columns are missing
        col1 = "Node"
        col2 = "Edges"
        col3 = "Color"
        width1 = max(len(col1), max((len(str(n["id"])) for n in node_stats), default=0))
        width2 = max(
            len(col2),
            max(
                (len(str(n["degree"])) for n in node_stats if n["degree"] is not None),
                default=0,
            ),
        )
        width3 = max(
            len(col3),
            max(
                (len(str(n["color"])) for n in node_stats if n["color"] is not None),
                default=0,
            ),
        )
        print(f"\n{col1:<{width1}} | {col2:<{width2}} | {col3:<{width3}}")
        print(f"{'-'*width1}-+-{'-'*width2}-+-{'-'*width3}")
        for n in node_stats:
            degree = n["degree"] if n["degree"] is not None else "-"
            color = n["color"] if n["color"] is not None else "-"
            print(f"{n['id']:<{width1}} | {degree:<{width2}} | {color:<{width3}}")


# --- Edge Creation Functions ---


def add_linear_edges(data, net, operation):
    """
    Add edges for any linear relationship where entries are lists of node names.

    This function infers edge creation logic based on the structure of the data:
    - If an entry is a list (or nested lists), it creates edges between consecutive nodes.
    - If an entry is a dict with an 'items' field, it recursively processes those items.
    - Edge styles and titles can be overridden at the entry or block level.

    Args:
        data: Section data (list or dict with 'items'), containing lists of node names.
        net (Network): pyvis Network object.
        operation (str): Relationship type (used for config and default title).
    """
    if isinstance(data, dict) and "items" in data:
        data = data["items"]

    for entry in data:
        # Extract edge style from entry['edge'] if present, else empty dict
        style = entry.get("edge", {}) if isinstance(entry, dict) else {}
        edge_kwargs = get_kwargs(
            entry_style=style,
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


def add_branching_edges(data, net, operation):
    """
    Add edges for any relationship type that uses 'from' and 'to' fields.
    For example: convergence, divergence, or custom operations.

    For each combination of 'from' and 'to', adds an edge from 'from' to 'to'.
    If the operation is 'convergence', sets arrows='from'.
    If the operation is 'divergence', sets arrows='to'.
    Otherwise, does not set the arrows attribute (uses pyvis default).

    Args:
        data: Section data (list or dict with 'items').
        net (Network): pyvis Network object.
        operation (str): Relationship type (e.g., 'convergence', 'divergence', or custom).
    """

    def to_list(val):
        if val is None:
            return []
        if isinstance(val, list):
            return val
        return [val]

    def add_entry(entry, block={}):
        if not isinstance(entry, dict):
            return
        from_vals = to_list(entry.get("from", []))
        to_vals = to_list(entry.get("to", []))
        style = entry.get("edge", {})
        block_style = block.get("edge", {})
        edge_kwargs = get_kwargs(
            entry_style=style,
            operation=operation,
            block_style=block_style,
            config_key="edge",
        )
        edge_kwargs["title"] = entry.get("title", block.get("title", operation))
        if ("arrows" not in edge_kwargs) and (
            operation in ["convergence", "divergence"]
        ):
            edge_kwargs["arrows"] = "to"

        for f in from_vals:
            for t in to_vals:
                net.add_edge(f, t, **edge_kwargs)

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


def add_clique_edges(data, net):
    """
    Add edges for a 'clique' (complete graph) operation.
    For each list of nodes, connect every pair of nodes.
    Supports both directed and undirected graphs based on config.

    Args:
        data: Section data (list or dict with 'items'), containing lists of node names.
        net (Network): pyvis Network object.
        operation (str): Relationship type (used for config and default title).
    """
    if isinstance(data, dict) and "items" in data:
        data = data["items"]

    for entry in data:
        style = entry.get("edge", {}) if isinstance(entry, dict) else {}
        edge_kwargs = get_kwargs(
            entry_style=style,
            operation="complete",
            config_key="edge",
        )
        edge_kwargs["title"] = (
            entry.get("title") if isinstance(entry, dict) else "complete"
        )
        # Extract node list
        items = (
            entry["items"] if isinstance(entry, dict) and "items" in entry else entry
        )
        nodes = list(flatten_items(items))
        n = len(nodes)
        for i in range(n):
            for j in range(i + 1, n):
                net.add_edge(nodes[i], nodes[j], **edge_kwargs)


# --- Main Network Construction ---


def build_network(yaml_path):
    """
    Build an interactive relationship network from a YAML file.
    Loads configuration, downloads images, adds nodes and edges, applies all options, and scales node sizes.
    Args:
        yaml_path (str): Path to the YAML configuration file.
    Returns:
        Network: Configured pyvis Network object.
    """
    global config
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)

    cfg = data.pop("config", {})
    config = Config(config=cfg)

    node_info = get_nodes(data=data)

    net = Network(**config.get("network"))
    net.options = set_options()

    if config.get("download_images", False):
        try:
            from imageManager import download

            download(node_info.keys(), config=config)
        except ImportError as e:
            print(f"[Warning] Could not import 'download' from imageManager: {e}")
        except Exception as e:
            print(f"[Error] Exception during image downloading: {e}")

    node_scale_factor = config.get("node").pop("scale_factor", 0)
    node_recolor = config.get("node").pop("recolor", False)
    node_print_table = config.get("node").pop("table", False)

    for item in sorted(node_info.keys()):
        node_info[item]["title"] = item

        try:
            from imageManager import filename

            node_info[item]["image"] = filename(item)
        except ImportError as e:
            print(f"[Warning] Could not import 'filename' from imageManager: {e}")
        except Exception as e:
            print(f"[Error] Exception assigning image filename for node '{item}': {e}")

        net.add_node(item, **node_info[item])

    for section, section_data in data.items():
        if section == "complete":
            add_clique_edges(data=section_data, net=net)
            continue
        if section_has_branching(section_data):
            add_branching_edges(data=section_data, net=net, operation=section)
        else:
            add_linear_edges(data=section_data, net=net, operation=section)

    # --- Post-processing: scale node size by degree ---
    if node_scale_factor > 0 or node_recolor or node_print_table:
        edit_nodes(
            net,
            scale_factor=node_scale_factor,
            recolor=node_recolor,
            print_table=node_print_table,
        )

    show_buttons = config.get("buttons").get("show", False)
    if show_buttons:
        filter = config.get("buttons").get("filter", True)
        net.show_buttons(filter_=filter)

    return net


# --- Script Entry Point ---

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
    output_path = os.path.abspath(f"{base_name}.html")
    net.save_graph(output_path)
    print("Network saved to:", output_path)

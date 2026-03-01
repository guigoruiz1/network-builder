# --- Imports ---

import yaml
import os
import sys
import argparse
from pyvis.options import Options
from pyvis.network import Network
from collections import Counter

# --- Global Configuration ---


class Config:
    """
    Configuration handler for network visualization settings.
    Supports deep merging of default and user-provided configs, and dictionary-style access.
    """

    default = {
        "node": {
            "scale_factor": 0,
            "font": {"size": 5},
            "shape": "image",
            "shapeProperties": {"useBorderWithImage": True},
        },
        "buttons": {
            "show": False,
            "filter": ["physics", "interaction", "layout"],
        },
        "network": {"height": "85vh", "select_menu": True, "directed": True},
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


def set_physics_options(physics_obj, config: dict) -> None:
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


def set_edge_options(edges_obj, config: dict) -> None:
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


def set_layout_options(layout_obj, config: dict) -> None:
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


def get_options():
    """
    Create and configure a pyvis Options object using the global config.
    Delegates to helper functions for each sub-object (physics, edges, layout, interaction, configure).
    Returns:
        Options: Fully configured pyvis Options object.
    """
    global config

    options = Options(layout=bool(config.get("layout")))
    # Use dictionary-style access for sub-objects
    if config.get("options"):
        if isinstance(config["options"], dict):
            import json

            options_json = json.dumps(config.get("options"))
        else:
            options_json = config.get("options")

        new_options = options.set(options_json)
        merge = new_options.pop("merge", False)
        if not merge:
            return new_options
        else:
            for key, value in new_options.items():
                if value is not None:
                    setattr(options, key, value)

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
    """
    Recursively flattens nested lists or single items into a generator of items.
    Args:
        items: An item to flatten.
    Yields:
        Individual items from the input.
    """
    if isinstance(items, str):
        yield items
    elif isinstance(items, list):
        for el in items:
            yield from flatten_items(el)
    elif items is not None:
        yield items


def get_kwargs(entry_style: dict, section: str, config_key: str = "edge") -> dict:
    """
    Merge styling options from config and YAML overrides for a given relationship entry.
    Args:
        entry_style (dict): Entry level style overrides.
        section (str): Section name (e.g., "series", "parallel", etc.).
        config_key (str): Which config key to use ('edge' or 'node').
    Returns:
        dict: Keyword arguments for pyvis.
    """
    global config
    base = config.get(config_key)
    op = config.get("section")
    op = op.get(section, {}) if section else {}
    op = op.get(config_key, {})
    merged = Config.deep_merge_dicts(base, op)
    merged = Config.deep_merge_dicts(merged, entry_style)
    return merged


# --- Node Collection and Editing ---


def get_nodes(data):
    """
    Collect all unique node names from the YAML data across all relationship sections.
    Merges any node-specific kwargs from the blocks and entries, including block-level and entry-level node styles.

    Args:
        data: The YAML data dictionary containing sections and node information.
    Returns:
        dict: Mapping of node names to their merged kwargs.
    """

    node_info = {}

    def add_node(name, section, style={}):
        node_kwargs = get_kwargs(
            entry_style=style,
            section=section,
            config_key="node",
        )

        if name not in node_info:
            node_info[name] = node_kwargs
        else:
            node_info[name] = Config.deep_merge_dicts(node_info[name], node_kwargs)

    for section in data:
        for block in data[section]:
            block_style = block.get("node", {}) if isinstance(block, dict) else {}
            # If block has 'items', iterate entries; else treat block as entry
            entries = (
                block["items"]
                if isinstance(block, dict) and "items" in block
                else [block]
            )
            for entry in entries:
                entry_style = entry.get("node", {}) if isinstance(entry, dict) else {}
                style = Config.deep_merge_dicts(block_style, entry_style)
                # If entry is a dict with 'from' or 'to', treat as branching; else treat as linear list
                if isinstance(entry, dict):
                    if ("from" in entry) and ("to" in entry):
                        for name in flatten_items(entry["from"]):
                            add_node(name, section, style)
                        for name in flatten_items(entry["to"]):
                            add_node(name, section, style)
                    elif "items" in entry:
                        for name in flatten_items(entry["items"]):
                            add_node(name, section, style)
                else:
                    # Treat as a list of node names (linear)
                    for name in flatten_items(entry):
                        add_node(name, section, style)

    return node_info


def edit_nodes(
    net: Network,
    scale_factor: float = 0,
    recolor: bool = False,
    print_table: bool = False,
) -> None:
    """
    Edit node properties in a pyvis Network object.
    Optionally scale node size by degree, recolor nodes by edge color majority, and print a summary table.
    If recoloring, nodes in groups with specific options are skipped to avoid overwriting group colors.

    Args:
        net (Network): pyvis Network object.
        scale_factor (float, optional): If set, increases node size by (scale_factor * degree).
        recolor (bool, optional): If True, recolors node to the most common color among its edges.
        print_table (bool, optional): If True, prints a table of node degrees and new colors.
    """
    node_stats = []
    adj_list = net.get_adj_list()
    for node in net.nodes:
        node_id = node["id"]

        if net.directed:
            outgoing = len(adj_list.get(node_id, []))
            incoming = sum(node_id in targets for targets in adj_list.values())
            degree = outgoing + incoming
        else:
            degree = len(adj_list[node_id])

        color = node.get("color")

        if scale_factor > 0:
            base_size = node.get("size", 25)
            node["size"] = base_size / 2 + scale_factor * degree

        if recolor:
            group_configs = config.get("options", {}).get("groups", {})
            if not (
                node.get("group") in group_configs
                and group_configs[node["group"]].get("color")
            ):  # Skip recoloring if node is in a group with a specified color
                connected_edges = [
                    e for e in net.edges if e["from"] == node_id or e["to"] == node_id
                ]
                colors = [e.get("color") for e in connected_edges if e.get("color")]
                if colors:
                    most_common_color, _ = Counter(colors).most_common(1)[0]
                    node["color"] = most_common_color
                    color = most_common_color

        node_stats.append({"id": node_id, "degree": degree, "color": color})

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


def add_linear_edges(entry, net: Network, section: str, block_style: dict = {}) -> None:
    """
    Add edges for any linear relationship where entries are lists of node names.

    This function infers edge creation logic based on the structure of the data:
    - If an entry is a list (or nested lists), it creates edges between consecutive nodes.
    - If an entry is a dict with an 'items' field, it recursively processes those items.
    - Edge styles can be overridden at the entry or block level.

    Args:
        entry: Entry (list or dict with 'items'), containing lists of node names.
        net (Network): pyvis Network object.
        section (str): Section name (e.g., 'series', 'parallel', etc.).
        block (dict): Optional block-level context for styling.
    """
    style = Config.deep_merge_dicts(
        block_style, entry.get("edge", {}) if isinstance(entry, dict) else {}
    )
    closed = style.pop("closed", False)
    edge_kwargs = get_kwargs(
        entry_style=style,
        section=section,
        config_key="edge",
    )
    edge_kwargs["title"] = edge_kwargs.get("title") or section

    items = entry["items"] if isinstance(entry, dict) and "items" in entry else entry

    for i in range(len(items) - 1):
        if isinstance(items[i], list):
            for sub in items[i]:
                net.add_edge(sub, items[i + 1], **edge_kwargs)
        else:
            net.add_edge(items[i], items[i + 1], **edge_kwargs)

    if closed and len(items) > 2:
        net.add_edge(items[-1], items[0], **edge_kwargs)


def add_branching_edges(
    entry, net: Network, section: str, block_style: dict = {}
) -> None:
    """
    Add edges for any relationship type that uses 'from' and 'to' fields.
    For example: convergence, divergence, or custom sections.

    For each combination of 'from' and 'to', adds an edge from 'from' to 'to'.

    Args:
        data: Section data (list or dict with 'items').
        net (Network): pyvis Network object.
        section (str): Section name (e.g., 'convergence', 'divergence', or custom).
        block_style (dict): Optional block-level context for styling.
    """

    def to_list(val):
        if val is None:
            return []
        if isinstance(val, list):
            return val
        return [val]

    def add_entry(e, block_style=None):
        if not isinstance(e, dict):
            return
        from_vals = to_list(e.get("from", []))
        to_vals = to_list(e.get("to", []))
        style = Config.deep_merge_dicts(
            block_style, e.get("edge", {}) if isinstance(e, dict) else {}
        )
        edge_kwargs = get_kwargs(
            entry_style=style,
            section=section,
            config_key="edge",
        )
        edge_kwargs["title"] = edge_kwargs.get("title") or section

        for f in from_vals:
            for t in to_vals:
                net.add_edge(f, t, **edge_kwargs)

    add_entry(entry, block_style)


def add_clique_edges(entry, net: Network, section: str, block_style: dict = {}) -> None:
    """
    Add edges for a 'clique' (complete graph) section.
    For each list of nodes, connect every pair of nodes.
    Supports both directed and undirected graphs based on config.

    Args:
        data: Section data (list or dict with 'items'), containing lists of node names.
        net (Network): pyvis Network object.
        section (str): Section name.
        block_style (dict): Optional block-level context for styling.
    """
    style = Config.deep_merge_dicts(
        block_style, entry.get("edge", {}) if isinstance(entry, dict) else {}
    )
    edge_kwargs = get_kwargs(
        entry_style=style,
        section=section,
        config_key="edge",
    )
    edge_kwargs["title"] = edge_kwargs.get("title") or "complete"

    if "arrows" not in edge_kwargs:
        edge_kwargs["arrows"] = "none"

    # Extract node list
    items = entry["items"] if isinstance(entry, dict) and "items" in entry else entry
    nodes = list(flatten_items(items))
    n = len(nodes)
    for i in range(n):
        for j in range(i + 1, n):
            net.add_edge(nodes[i], nodes[j], **edge_kwargs)


def add_edges(data, net: Network, section: str) -> None:
    """
    Dispatch entries in a section to the appropriate edge-creation function.

    Iterates blocks/entries in `data`. For each entry, if the entry (or any
    nested entry) contains `from`/`to` it's treated as branching and
    `add_branching_edges` is called for that entry; otherwise `add_linear_edges`
    is called.

    Args:
        data: Section data (list or dict with 'items').
        net (Network): pyvis Network object.
        section (str): Section name.
    """
    # Normalise to list of blocks/entries
    entries = []
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict) and "items" in data:
        entries = data["items"]
    else:
        entries = [data]

    def add_entry(entry, block_style={}):
        if isinstance(entry, dict):
            if ("from" in entry) and ("to" in entry):
                add_branching_edges(
                    entry, net=net, section=section, block_style=block_style
                )
            elif "items" in entry:
                # Recursively process nested blocks in items
                for subentry in entry["items"]:
                    add_entry(
                        subentry,
                        block_style=Config.deep_merge_dicts(
                            block_style, entry.get("edge", {})
                        ),
                    )
            else:
                print(
                    f"[WARN] Unrecognized entry format in section '{section}': {entry}"
                )
        elif isinstance(entry, list):
            closed = get_kwargs(
                entry_style=block_style,
                section=section,
                config_key="edge",
            ).pop("closed", False)
            if closed == "complete":
                add_clique_edges(
                    entry, net=net, section=section, block_style=block_style
                )
            else:
                add_linear_edges(
                    entry, net=net, section=section, block_style=block_style
                )

    for block in entries:
        block_style = block.get("edge", {}) if isinstance(block, dict) else {}
        if isinstance(block, dict):
            add_entry(block, block_style=block_style)
        else:
            add_entry(block, block_style=block_style)


# --- Main Network Construction ---


def build_network(yaml_path: str) -> Network:
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

    node_scale_factor = config.get("node").pop("scale_factor", 0)
    node_recolor = config.get("node").pop("recolor", False)
    node_print_table = config.get("node").pop("table", False)

    node_info = get_nodes(data=data)

    net = Network(**config.get("network"))
    net.options = get_options()

    if config.get("download_images", False):
        try:
            from imageManager import download

            download(node_info.keys(), config=config)
        except ImportError as e:
            print(f"[Warning] Could not import 'download' from imageManager: {e}")
        except Exception as e:
            print(f"[Error] Exception during image downloading: {e}")

    for item in sorted(node_info.keys()):
        node_info[item]["title"] = item  # Maybe remove
        if (
            "image" in node_info[item]["shape"]
        ):  # Only assign image for image-type nodes
            try:
                from imageManager import filename

                file_name = filename(item)
                if file_name:
                    node_info[item]["image"] = file_name

            except ImportError as e:
                print(f"[Warning] Could not import 'filename' from imageManager: {e}")
            except Exception as e:
                print(
                    f"[Error] Exception assigning image filename for node '{item}': {e}"
                )

        net.add_node(item, **node_info[item])

    for section, section_data in data.items():
        add_edges(data=section_data, net=net, section=section)

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

    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    self_dir = os.path.dirname(os.path.abspath(__file__))

    net = build_network(args.yaml_file)

    base_name = os.path.splitext(os.path.basename(args.yaml_file))[0]
    output_path = os.path.abspath(f"{base_name}.html")

    # Add template if it exists in the script path. If not set, pyvis will use its default template.
    template_path = os.path.join(self_dir, "template.html")
    if os.path.exists(template_path):
        net.set_template(template_path)

    net.save_graph(output_path)
    print("Network saved to:", output_path)

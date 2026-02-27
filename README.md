# Relationship Network Visualisation

## Overview

This project enables flexible visualisation of relationships, transformations, and groupings between entities as an interactive network using [pyvis](https://pyvis.readthedocs.io/).

You define your data and configuration in a YAML file, specifying sequences, branches, combinations, and custom styling. The script reads this YAML and generates a rich HTML network:

- Nodes can display images, custom shapes, and tooltips.
- Edges are colored and styled according to relationship type or custom overrides.
- Interactive controls allow you to explore, filter, and adjust the network live in your browser.
- All visual and behavioural options are configurable.
- Image downloading is handled by user-defined functions for maximum flexibility.

Whether you want to visualise processes, hierarchies, or complex relationships, this tool provides a highly customisable and extensible framework for network visualisation.

---

## 1. Example YAML Blocks

The section names you choose are not hard-coded — the examples below (`series`, `parallel`, `convergence`, `divergence`, etc.) are conventional titles. The script determines processing based on each section's entry structure.

### Sequential Relationships
```yaml
series:
  - title: "Evolution"
    items:
      - ["Caterpillar", "Chrysalis", "Butterfly"]
      - ["Seed", "Sprout", "Plant", "Flower"]
  - title: "Process Steps"
    items: 
      - ["Draft", "Review", "Approval", "Publication"]
```

### Parallel Relationships
```yaml
parallel:
  - items:
    - ["Left", "Right"]
    - ["North", "South"]
    edge:
      arrows: "none"
```

`series` and `parallel` in these examples are sections with list-like entries. These are processed by the linear-edge backend `add_linear_edges`, where each node is connected to its immediate neighbour.

### Convergence
```yaml
convergence:
  - title: "Combination"
    items:
      - from: ["Salt", "Water"]
        to: "Saltwater"
      - from: ["Flour", "Eggs", "Milk"]
        to: "Pancake Batter"
```

### Divergence
```yaml
divergence:
  - title: "Branches"
    items:
      - from: "Tree"
        to:
          - "Branch1"
          - "Branch2"
```

`convergence` and `divergence` in these examples contain entries with `from`/`to` keys. These are processed by the branching-edge backend `add_branching_edges`, where all nodes in `from` are connected to all nodes in `to`.

### Complete (Clique) Relationships
```yaml
complete:
  - title: "Letters"
    items: 
      - ["X", "Y", "Z"]
```

`complete` is a special case which connects all nodes in each list (complete subgraph).

## 2. Edge/Node Overrides

You can override edge and node properties at the block or entry level:
```yaml
series:
  - title: "Special Chain"
    edge:
      color: "red"
    items:
      - ["Step1", "Step2", "Step3"]
      - title: "Subchain"
        edge:
          color: "green"
        items: 
          - ["SubstepA", "SubstepB"]

parallel:
  - title: "Highlighted Pair"
    edge:
      color: "orange"
      smooth: false
    items:
      - ["Alpha", "Beta"]

convergence:
  - title: "Custom Merge"
    items:
      - from: ["A", "B"]
        to: "AB"
        edge:
          color: "pink"

divergence:
  - title: "Special Branch"
    edge:
      color: "teal"
    items:
      - from: "Origin"
        to:
          - "BranchX"
```

Block- and entry-level dictionaries provided under `node` or `edge` are forwarded as keyword arguments to pyvis when nodes and edges are created. A few special node options — `scale_factor`, `table`, and `recolor` — are consumed (popped) by the script for post-processing and are not passed through to pyvis; see section 6 for details.

---

## 3. Config Section Details

The `config` block controls all global visual and behavioural options. Example:
```yaml
config:
  buttons:
    show: True
    filter: [physics, interaction]
  node:
    scale_factor: 10
    size: 100
    borderWidthSelected: 4
  edge:
    width: 20
    arrowStrikethrough: False
  section:
      series:
        edge:
          color: orange
      convergence:
        edge:
          color: purple
          smooth: true
      parallel:
        edge:
          color: green
          smooth: false
          arrows: "none"
      divergence:
        edge:
          color: red
  physics:
    enabled: true
    repulsion:
      node_distance: 1000
      central_gravity: 0.2
      spring_length: 200
      spring_strength: 0.015
      damping: 0.5
  network:
    height: "90vh"
    width: "100%"
    select_menu: true
  interaction:
    navigationButtons: true
  download_images: true
```
- **Key Options:**
- `node`: Appearance of nodes.
- `edge`: Appearance of edges.
- `section`: Per-section edge/node defaults.
- `interaction`: Navigation and drag controls.
- `physics`: Controls force-directed layout.
- `network`: Network initialisation parameters.
- `download_images`: Toggle image downloading.

Node and edge configuration options in the `config` block are applied globally to all nodes and edges unless overridden. Per-section defaults placed under the `section` key (for example `section.series.edge`) provide defaults for node/edge styles applied to that section and are applied before any block- or entry-level overrides. To customize properties for a specific entry (such as size, shape, label, or any pyvis-supported attribute), use the `node:` or `edge:` key at the block or entry level in your YAML file. For example:
```yaml
series:
  - items:
      - ["A", "B", "C"]
    node:
      size: 120
      shape: "image"
    edge:
      color: "blue"
      width: 10
```
If you need to further modify an individual node or edge after building the network, you can access the node or edge from the returned `net` object and apply changes directly in Python.

**Note:** A node can appear in multiple sections or entries. Node attributes are merged as entries are processed; when the same attribute is provided multiple times, the last occurrence (the most recently processed entry) wins and will overwrite earlier values for that attribute.

### Script Default Config

The script loads a default Config object with the following attributes for convenience:
```yaml
node:
  scale_factor: 0
  shape: image
  font: 
    size: 5
  shapeProperties:
    useBorderWithImage: true
buttons:
  show: false
  filter:
    - physics
    - interaction
network:
  directed: True
  height: "85vh"
  select_menu: true
download_images: false
```

---

## 4. Image Downloading

Image downloading is handled by user-defined external functions, which you can customize as needed. The script expects `download_images` and `image_filename` functions to be available (imported from a `imageManager.py` module).

- `download_images(names, config)`: Downloads images for each node name, passing a configuration options object to incorporate the YAML config fields.
- `image_filename(name)`: Returns the filename for a given node name, allowing you to control naming conventions, file extensions, or directory structure. This is used to assign image paths to each node.

You can extend these functions to support custom image sources (local, remote, API), cropping, resizing, or format conversion. The script will call them automatically if `download_images` is enabled in the config. If you do not want images, set `download_images: false` in your YAML config.

---

## 5. Pyvis Options Menu & Interactive Controls

- **Options menu:**
  - Enable with `config.buttons.show: true`.
  - Filter menu groups with `config.buttons.filter` (e.g., `[physics, interaction]`).
- **Controls:**
  - Navigation buttons: Enable with `config.interaction.navigationButtons: true`.
  - Drag nodes/edges: Set `dragNodes`, `hideEdgesOnDrag`, `hideNodesOnDrag` in `config.interaction`.
- **Menu features:**
  - Adjust physics, layout, and appearance live in the browser.
  - Save and restore network state.

---

## 6. Node Scaling and Recoloring Logic

- **Node scaling:**
  - Controlled by `config.node.scale_factor` (numeric value).
  - If set to a value greater than 0, after all edges are added, each node's size is increased by `scale_factor * degree`.
  - Degree is the number of edges connected to each node (both incoming and outgoing).
  - This helps visually emphasize more connected nodes.

- **Node recoloring:**
  - Controlled by `config.node.recolor` (boolean).
  - If enabled, each node is recolored to match the most common color among its connected edges.
  - This can help visually group nodes by relationship type or highlight network structure.

- **Node table output:**
  - If `config.node.table` is set to `True`, a summary table of node degrees and colors is printed to the console after building the network.

---

## 7. Usage

### 1. Prepare your YAML file
Describe entities and relationships as shown in the examples above.

### 2. Run as a script

To generate the network HTML directly from the command line:

```bash
python network.py network.yaml
```

This will create `network.html` in the current directory. Open it in your web browser to view the interactive network.

### 3. Use as a module

To integrate into your own Python scripts:

```python
from network import build_network
net = build_network('your_data.yaml')
net.show('network.html')  # Opens the visualisation in your browser
```

You can further customize the `net` object before saving or displaying.

---

## 8. Troubleshooting

- **Missing images:**
  - Check your image handling function and internet connection.
  - Set `download_images: false` to skip image fetching.
  - Ensure entity names match your image source logic.
- **Dependency issues:**
  - Install required packages: `pip install pyvis pillow pyyaml requests`.
- **YAML formatting errors:**
  - Use proper indentation and list syntax.
  - Validate YAML with online tools if needed.
- **Network performance:**
  - For large networks, adjust `physics` and `layout` settings.
- **Edge/Node appearance:**
  - Use block/entry overrides for color, smoothness, and title.

---

For further customization, see the script and YAML comments. For advanced usage, refer to the pyvis documentation.

---

NOTE: this script is not designed for hierarchical layouts or single node setting properties per individual node/edge!
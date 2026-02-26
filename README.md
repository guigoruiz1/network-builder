# Relationship Network Visualization

## Overview

This project enables flexible visualization of relationships, transformations, and groupings between entities as an interactive network using [pyvis](https://pyvis.readthedocs.io/).

You define your data and configuration in a YAML file, specifying sequences, branches, combinations, and custom styling. The script reads this YAML and generates a rich HTML network:

- Nodes can display images, custom shapes, and tooltips.
- Edges are colored and styled according to relationship type or custom overrides.
- Interactive controls allow you to explore, filter, and adjust the network live in your browser.
- All visual and behavioral options are configurable.
- Image downloading is handled by user-defined functions for maximum flexibility.

Whether you want to visualize processes, hierarchies, or complex relationships, this tool provides a highly customizable and extensible framework for network visualization.

---

## 1. Full Example YAML Blocks

### Sequential Relationships
```yaml
series:
  - title: "Evolution"
    items:
      - ["Caterpillar", "Chrysalis", "Butterfly"]
      - ["Seed", "Sprout", "Plant", "Flower"]
  - title: "Process Steps"
    items: ["Draft", "Review", "Approval", "Publication"]
```

### Parallel Relationships
```yaml
parallel:
  - title: "Counterparts"
    items:
      - ["Sun", "Moon"]
      - ["North", "South"]
```

### Convergence (Combining Entities)
```yaml
convergence:
  - title: "Combination"
    items:
      - materials: ["Salt", "Water"]
        product: "Saltwater"
      - materials: ["Flour", "Eggs", "Milk"]
        product: "Pancake Batter"
```

### Divergence (Branching Entities)
```yaml
divergence:
  - title: "Branches"
    items:
      - root: "Tree"
        branches:
          - "Branch1"
          - "Branch2"
```

### Edge/Block Overrides (All Relationship Types)
You can override edge and node properties at the block or entry level in any relationship type (series, parallel, convergence, divergence) using the new syntax:
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
        items: ["SubstepA", "SubstepB"]

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
      - materials: ["A", "B"]
        product: "AB"
        edge:
          color: "pink"

divergence:
  - title: "Special Branch"
    edge:
      color: "teal"
    items:
      - root: "Origin"
        branches:
          - "BranchX"
```

---

## 2. Config Section Details

The `config` block controls all global visual and behavioral options. Example:
```yaml
config:
  buttons:
    show: True
    filter: [physics, interaction]
  node:
    scale_factor: 10
    shape: image
    size: 100
    borderWidthSelected: 4
  edge:
    width: 20
    arrowStrikethrough: False
  operation:
      series:
        edge:
          color: orange
          smooth: true
      convergence:
        edge:
          color: purple
          smooth: true
      parallel:
        edge:
          color: green
          smooth: false
      divergence:
        edge:
          color: red
          smooth: true
  physics:
    enabled: true
    repulsion:
      node_distance: 1000
      central_gravity: 0.2
      spring_length: 200
      spring_strength: 0.015
      damping: 0.09
  network:
    height: 90vh
    width: 100%
    directed: true
    select_menu: true
  interaction:
    navigationButtons: true
  download_images: true
```

**Key Options:**
- `buttons`: Show pyvis options menu, filter menu groups.
- `node`: Appearance of nodes.
- `edge`: Appearance of edges.
- `operation`: Per-relationship edge defaults.
- `physics`: Controls force-directed layout.
- `network`: Network dimensions and directionality.
- `interaction`: Navigation and drag controls.
- `download_images`: Toggle image downloading.

**Note:**
Node and edge configuration options in the `config` block are applied globally to all nodes and edges unless overridden. To customize properties for a specific entry (such as size, shape, label, or any pyvis-supported attribute), use the `node:` or `edge:` key at the block or entry level in your YAML file. For example:
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

Arrows are handled automatically by the script logic based on relationship type.

---

## 3. Image Downloading & Cropping

Image downloading and cropping are handled by user-defined external functions, which you can customize as needed. The script expects `download_images` and `image_filename` functions to be available (imported from a `imageManager.py` module).

- `download_images(names, config)`: Downloads images for each node name, passing a configuration options object to incorporate the YAML config fields.
- `image_filename(name)`: Returns the filename for a given node name, allowing you to control naming conventions, file extensions, or directory structure. This is used to assign image paths to each node.

You can extend these functions to support custom image sources (local, remote, API), cropping, resizing, or format conversion. The script will call them automatically if `download_images` is enabled in the config. If you do not want images, set `download_images: false` in your YAML config.

---

## 4. Extending the Network

- **Add new relationships:** Add blocks to `series`, `parallel`, `convergence`, or `divergence`.
- **Custom node/edge appearance:** Override parameters at block or entry level in any relationship type.

---

## 5. Troubleshooting

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

## 6. Pyvis Options Menu & Interactive Controls

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
net.show('network.html')  # Opens the visualization in your browser
```

You can further customize the `net` object before saving or displaying.

---


## 8. Node Scaling and Recoloring Logic

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

For further customization, see the script and YAML comments. For advanced usage, refer to the pyvis documentation.

---

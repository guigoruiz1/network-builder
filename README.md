# Generalized Relationship Network Visualization

## Overview

This project visualizes relationships between entities as an interactive network using [pyvis](https://pyvis.readthedocs.io/). Relationships, transformations, and groupings are defined in a YAML file, and the script generates a rich HTML network with entity images, colored edges, and tooltips.

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
    color: "blue"
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
You can override edge color, smoothness, and title at the block or entry level in any relationship type (series, parallel, convergence, divergence):
```yaml
series:
  - title: "Special Chain"
    color: "red"
    items:
      - ["Step1", "Step2", "Step3"]
      - title: "Subchain"
        color: "green"
        items: ["SubstepA", "SubstepB"]
parallel:
  - title: "Highlighted Pair"
    color: "orange"
    smooth: false
    items:
      - ["Alpha", "Beta"]
convergence:
  - title: "Custom Merge"
    color: "purple"
    items:
      - materials: ["A", "B"]
        product: "AB"
divergence:
  - title: "Special Branch"
    color: "teal"
    items:
      - root: "Origin"
        branches:
          - "BranchX"
```

---

## 2. Config Section Details

The `config` block controls all visual and behavioral options. Example:
```yaml
config:
  buttons:
    show: True
    filter: [physics, interaction]
  node:
    scale: True
    scale_factor: 10
    shape: image
    size: 100
    borderWidthSelected: 4
  edge:
    width: 20
    arrowStrikethrough: False
  operation:
    series:
      color: orange
      smooth: true
    convergence:
      color: purple
      smooth: true
    parallel:
      color: green
      smooth: false
    divergence:
      color: red
      smooth: true
  sizes:
    ref: [690, 1000]
    offset: [82, 182]
    crop: [528, 522]
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
- `node`: Appearance and scaling of nodes.
- `edge`: Appearance of edges.
- `operation`: Per-relationship edge defaults.
- `sizes`: Image cropping parameters (short lists like `ref: [690, 1000]` are supported).
- `physics`: Controls force-directed layout.
- `network`: Network dimensions and directionality.
- `interaction`: Navigation and drag controls.
- `download_images`: Toggle image downloading.

**Note:**
Node and edge configuration options in the config block are applied equally to all nodes and edges. Only `color`, `smooth`, and `title` are individually set by the YAML file (arrows are handled by the script logic). If you wish to modify a property of a particular node or edge (e.g., size, shape, label), you should do so by accessing the node from the returned network object (`net`) and applying the change directly in Python after building the network.

---

## 3. Image Downloading & Cropping

Image downloading and cropping are handled by user-defined external functions, which you can import and customize as needed. The script expects these functions to be available for handling image filenames, cropping, and downloading. This allows you to tailor image processing to your own requirements.

---

## 4. Extending the Network

- **Add new relationships:** Add blocks to `series`, `parallel`, `convergence`, or `divergence`.
- **Custom node/edge appearance:** Override `color`, `smooth`, `title` at block or entry level in any relationship type.
- **Add new relationship types:** Extend the script with new YAML keys and edge logic.
- **Custom tooltips:** Set `title` in blocks or entries for custom edge tooltips.
- **Node scaling:** Adjust `scale` and `scale_factor` in `config.node`.

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

1. **Prepare your YAML file** describing entities and relationships as shown above.
2. **Call `build_network(yaml_path)`** in your script, passing the path to your YAML file.
3. **Work with the returned `net` object** (a pyvis Network), or save it directly to HTML:
   ```python
   net = build_network('your_data.yaml')
   net.show('network.html')
   ```

---

## 8. Node Scaling Logic & Degree Calculation

- **Node scaling:**
  - Controlled by `config.node.scale` and `config.node.scale_factor`.
  - After adding all edges, node size is increased by `scale_factor * degree`.
- **Degree calculation:**
  - Degree = number of outgoing edges for each node.
  - Table of node degrees is printed to console after network build.

---

For further customization, see the script and YAML comments. For advanced usage, refer to the pyvis documentation.

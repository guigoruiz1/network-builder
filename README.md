# Relationship Network Visualisation

You can see a live example [here](https://ruizbad.com/network-builder/example/example.html).

## Overview

This tool builds interactive network visualisations from a compact YAML description and renders them using [pyvis](https://github.com/WestHealth/pyvis).

You declare entities and relationships in YAML and specify styling. The script infers structure from the entries and constructs a network accordingly.

Highlights:
- Nodes may show images, custom shapes and tooltips.
- Edges can be coloured and styled.
- An interactive options menu lets you adjust physics, layout and appearance in the browser.
- Image handling is pluggable: you can control downloading, caching, and filenames.

**Note:**
This script is intended to create visual summaries from structured YAML input. It is not designed for hierarchical layouts or for configuring individual nodes/edges one-by-one. Instead, it applies block- and entry-level styles inferred from your YAML.

---

## 1. Example YAML blocks

Section names are not fixed — the examples shown (`series`, `parallel`, `convergence`, `divergence`, etc.) are conventional. The script decides how to process a section by inspecting the structure of its entries.

### Linear relationships
```yaml
series:
  - edge:
      title: "Evolution"
    items:
      - ["Caterpillar", "Chrysalis", "Butterfly"]
      - ["Seed", "Sprout", "Plant", "Flower"]
  - edge:
      title: "Process Steps"
    items: 
      - ["Draft", "Review", "Approval", "Publication"]

parallel:
  - items:
    - ["Left", "Right"]
    - ["North", "South"]
    edge:
      arrows: "none"
```

`series` and `parallel` above contain list-like entries and are treated as linear chains: each node is connected to its immediate neighbour.

### Branching relationships
```yaml
convergence:
    - from: ["Salt", "Water"]
      to: "Saltwater"
    - from: ["Flour", "Eggs", "Milk"]
      to: "Pancake Batter"

divergence:
  - edge:
      title: "Branches"
    items:
      - from: "Tree"
        to:
          - "Branch1"
          - "Branch2"
```

`convergence` and `divergence` use `from`/`to` mappings and are processed as branching relationships: every node in `from` connects to every node in `to`.

### Complete (clique) relationships
```yaml
complete:
  - edge:
      closed: "complete"
      title: "Letters"
    items: 
      - ["X", "Y", "Z"]
```

`complete` is a special case: each list is treated as a complete subgraph (every node connects to every other node in that list).

---

## 2. Edge and node overrides

Blocks are items in a section's list and usually include `items` plus optional `node` or `edge` defaults. An entry is an element of a block's `items` list; when a block has no `items` key the block itself acts as a single entry.

Block-level `node` and `edge` mappings act as defaults for the entries they directly contain. Entry-level `node` and `edge` mappings take precedence and override block defaults for that entry only. 


Example:
```yaml
series:
  - edge:
      title: "Special Chain"
      color: "red"
    items:
      - ["Step1", "Step2", "Step3"]
      - edge:
          title: "Subchain"
          color: "green"
        items: 
          - ["SubstepA", "SubstepB"]

parallel:
  - edge:
      title: "Highlighted Pair"
      color: "orange"
      smooth: false
    items:
      - ["Alpha", "Beta"]

convergence:
  - edge:
      title: "Merge"
    items:
      - from: ["A", "B"]
        to: "AB"
        edge:
          color: "pink"
          title: "Pink Merge"

divergence:
  - edge:
      title: "Special Branch"
      color: "teal"
    items:
      - from: "Origin"
        to:
          - "BranchX"
```

**Note:** 
The script accepts one level of entries and does not cascade into nested sub-blocks.

---

### Edge titles

`edge.title` overrides the title shown for an edge. If no title is provided, the script falls back to the containing section name (for example `series`, `convergence`, etc.).

## 3. Configuration (`config`)

The `config` block controls global visual and behavioural options. Example:
```yaml
config:
  buttons:
    show: True
    filter: ["physics", "interaction"]
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
          color: "orange"
      convergence:
        edge:
          color: "purple"
          smooth: True
      parallel:
        edge:
          color: "green"
          smooth: False
          arrows: "none"
      divergence:
        edge:
          color: "red"
  physics:
    enabled: True
    repulsion:
      node_distance: 1000
      central_gravity: 0.2
      spring_length: 200
      spring_strength: 0.015
      damping: 0.5
  network:
    height: "90vh"
    width: "100%"
    select_menu: True
  interaction:
    navigationButtons: True
  download_images: True
```

Key options:

- `node`: default node attributes.
- `edge`: default edge attributes.
- `section`: per-section defaults for nodes/edges.
- `interaction`: drag and navigation controls.
- `physics`: physics settings. 
- `network`: networkinitialization parameters such as height and width.
- `download_images`: enable image downloading.
 - `options`: The [vis.js](https://github.com/visjs/vis-network) options can be provided as a JSON string or in YAML syntax. If the argument `merge=True` is passed, these options will be merged with other configuration options instead of overwriting them.

### Script default config

For convenience the script supplies a default config when none is provided:
```yaml
node:
  scale_factor: 0
  shape: image
  font: 
    size: 5
  shapeProperties:
    useBorderWithImage: True
buttons:
  show: false
  filter:
    - physics
    - interaction
network:
  directed: True
  height: "85vh"
  select_menu: True
download_images: False
```

Note about `edge` vs `edges` and pyvis options

- Use `edge` (singular) in `config` and in block/entry mappings for per-edge attribute defaults (colour, width, arrows, etc.).
- Use `edges` (plural) in `config` to configure the pyvis Options `edges` sub-object (this controls pyvis rendering options, not per-edge attributes).

Also supported as top-level keys and mapped straight to pyvis Options sub-objects are: `physics`, `layout`, `interaction` and `configure`. These keys are forwarded to `get_options()` which applies them to the `Options` object used by pyvis.

---

## 4. Image handling

Image handling is pluggable. The code expects an `imageManager` module that exposes two functions. A template `imageManager` module is provided as a starting point; you can customize it to fit your needs:

- `imageManager.download(names, config)`: download or prepare images for the provided names.
- `imageManager.filename(name)`: return the filename or path to use for a given node name.

The script will attempt to import `download` and `filename` from `imageManager` and will print a warning if these are not available or raise errors if the functions fail at runtime. Implement these functions to support remote APIs, local caching, resizing or format conversion. When `config.download_images` is true, the script will call `imageManager.download(...)` before adding nodes.

---

## 5. Interactive controls and options menu

- Enable the options menu with `config.buttons.show: true` and tune visible groups via `config.buttons.filter` (for example `[physics, interaction]`).
- Show navigation buttons with `config.interaction.navigationButtons: true` and control drag behaviour using `dragNodes`, `hideEdgesOnDrag` and `hideNodesOnDrag`.
- The menu allows live adjustment of physics, layout and appearance and can save and restore network state.

---

## 6. Node scaling and recolouring

Script-level features are controlled by `config.node`:

- `scale_factor` (numeric): when greater than zero, after all edges are added, the script increases each node's size by `scale_factor * degree` (degree counts both incoming and outgoing edges).
- `recolor` (boolean): when enabled, a node is recoloured to match the most common colour among its incident edges.
- `table` (boolean): when enabled, the script prints a summary table of node degrees and colours once the network is built.

### Script-consumed keys

The script consumes (pops) the following keys from `node`/`edge` mappings; these keys are interpreted by the script and are not forwarded as pyvis attributes:

- `node.scale_factor`
- `node.recolor`
- `node.table`
- `edge.closed` — when true on a linear/list entry the list is treated as a closed circuit (the last node connects back to the first).

Keep these keys at block or entry level as required; they will be removed before pyvis receives node/edge attributes.

---

## 7. Usage

1. Prepare your YAML file following the examples and override rules above.

2. Run the script to produce an HTML visualisation:

```bash
python network.py network.yaml
```

The output HTML file will be named after your YAML file (e.g., `network.yaml` produces `network.html`) and saved in the current directory. You can override the output filename if desired. Open it in a browser to explore the interactive visualisation.

3. Use as a module:

```python
from network import build_network
net = build_network('your_data.yaml')
net.show('network.html')
```

You may further modify the returned `net` object before saving or displaying.

---

## 8. Troubleshooting

- Missing images: check your image functions and network access; set `download_images: false` to disable fetching.
- Dependencies: install required packages with `pip install pyvis pillow pyyaml requests`.
- YAML errors: ensure correct indentation and list syntax; validate with a YAML linter.
- Performance: for large graphs, tune `physics` and layout settings in `config`.
- Appearance: use block/entry `node`/`edge` overrides to control colour, smoothness and titles.

--- 

For further customisation consult the script's inline comments and the [pyvis](https://github.com/WestHealth/pyvis) documentation.

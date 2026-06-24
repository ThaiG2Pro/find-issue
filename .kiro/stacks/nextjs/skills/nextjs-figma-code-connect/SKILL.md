---
name: nextjs-figma-code-connect
description: >
  Connect Figma design components to code implementations via Figma MCP.
tags: [frontend, nextjs, figma]
---
# Skill: Figma Code Connect Components

Connect Figma design components to their code implementations in the CMS codebase. Scan for matching MUI/Vuexy components, present results, and send accepted mappings back to Figma.

## When to Use

- Mapping Figma components to existing MUI/Vuexy React components in `apps/cms/src/`
- After adding new CMS components that should be linked to Figma
- Before S4 Build to ensure developer sees correct code snippets in Figma Dev Mode
- When resolving UI bugs caused by design-code mismatch

## Prerequisites

- Figma MCP server connected (remote: `https://mcp.figma.com/mcp`)
- Figma file URL with design components

## Workflow

### Step 1: Get Figma Component Map

Call `get_code_connect_map` with the Figma file URL to see existing mappings:

```
get_code_connect_map(fileKey, nodeId)
```

Review which Figma components already have code connections and which are unmapped.

### Step 2: Get Suggestions

Call `get_code_connect_suggestions` to auto-detect matches between Figma components and codebase:

```
get_code_connect_suggestions(fileKey)
```

The tool scans the codebase for components matching Figma component names.

### Step 3: Review Matches

For each suggestion, verify:
- Figma component name matches the correct React component
- Component file path is correct (should be in `apps/cms/src/`)
- Component variant props align with Figma variants

### Step 4: Confirm Mappings

Send accepted mappings back to Figma:

```
send_code_connect_mappings(fileKey, mappings)
```

### Step 5: Verify in Figma Dev Mode

After mappings are sent, developers inspecting components in Figma Dev Mode will see actual code snippets from the codebase.

## Component Locations

When scanning for matches, prioritize these directories:

```
apps/cms/src/
├── components/           # Shared UI components
├── @core/components/     # Vuexy core components
├── views/                # Page-level view components
│   ├── brands/
│   ├── categories/
│   ├── attributes/
│   ├── suppliers/
│   ├── products/
│   ├── campaign-skus/
│   └── inventory/
└── @layouts/             # Layout components
```

## Component Mapping Rules

- MUI components (Button, TextField, DataGrid, etc.) → map to Vuexy-wrapped versions in `@core/`
- Custom components → map to `components/` or `views/` files
- Do NOT map to `node_modules` — always map to project source files
- Prefer the most specific component (e.g., `BrandForm` over generic `Form`)

## Integration with SDLC

| Phase | Action |
|-------|--------|
| S3 Design | Run `get_code_connect_map` to check existing mappings |
| S4 Build | After creating new components, run suggestions + send mappings |
| S5 QA | Verify mappings are current, use `figma-visual-qa` skill for visual check |

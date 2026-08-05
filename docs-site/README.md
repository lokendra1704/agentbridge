# docs-site

The agentbridge documentation site, authored as Markdown and synced to
[ReadMe](https://docs.readme.com/main/docs/about-readme) with the `rdme` CLI.

This directory is **not** part of the Python package. It ships no code and is excluded from
the build.

## Layout

```
docs-site/
├── README.md              this file — not synced
└── guides/                synced to the Guides section
    ├── about.md                     1  What is agentbridge?
    ├── quickstart.md                2  Quickstart
    ├── core-concepts.md             3  Core concepts
    ├── spec-reference.md            4  Spec reference        ← parent page
    │   ├── spec-workflow.md            └─ workflow.yaml
    │   ├── spec-agents.md              └─ Agents
    │   ├── spec-skills.md              └─ Skills
    │   └── spec-tools.md               └─ Tools
    ├── cli-reference.md             5  CLI reference
    ├── engine-mapping.md            6  Engine mapping
    ├── diagnostics.md               7  Diagnostics reference
    ├── deploying.md                 8  Deploying
    ├── architecture.md              9  Architecture
    └── adding-an-engine.md         10  Adding an engine
```

The indentation above is illustrative only. **`rdme` is directory-agnostic** — hierarchy comes
entirely from frontmatter (`category.uri`, `parent.uri`, `position`), never from where a file
sits on disk. All guide pages live flat in `guides/`.

## Frontmatter

Every page carries:

```yaml
---
title: Quickstart
category:
  uri: documentation      # the Guides category URI in your ReadMe project
slug: quickstart          # URL slug; defaults to the filename
position: 2               # order within the category
privacy:
  view: public
---
```

Child pages add a parent:

```yaml
parent:
  uri: spec-reference     # the parent page's slug
```

`title` and `category.uri` are required for initial page creation; neither is required for
subsequent updates.

> **Set `category.uri` to match your project.** `documentation` is ReadMe's conventional URI
> for the Guides category, but yours may differ. Check it in the ReadMe dashboard before the
> first sync — a wrong URI creates pages in the wrong place rather than failing.

## Syncing

Requires `rdme@10` or later (the version that targets ReadMe Refactored; `rdme@9` used a
different frontmatter shape).

```bash
npm install -g rdme

# Always dry-run first — it validates frontmatter without writing anything
npx rdme docs upload ./docs-site/guides --key "$README_API_KEY" --dry-run

# Then for real
npx rdme docs upload ./docs-site/guides --key "$README_API_KEY"
```

| Flag | Notes |
|---|---|
| `--key` | API key. Use an environment variable, never a literal |
| `--branch` | Target project version. Defaults to `stable` |
| `--dry-run` | Validate and report without uploading |

The command validates frontmatter before syncing and reports, per page, whether it is being
created or updated.

## Continuous sync

`.github/workflows/docs.yml` uploads on every push to `main` that touches this directory. It
needs a `README_API_KEY` repository secret.

Pull requests get a dry run instead, so frontmatter mistakes surface in review rather than in
production.

## Cross-references

ReadMe resolves `doc:` links by slug:

```markdown
See [Quickstart](doc:quickstart) and [Diagnostics](doc:diagnostics).
```

If you rename a page's `slug`, grep this directory for `doc:<old-slug>` before syncing.

## Keeping docs honest

Several pages quote real output and real values. When the implementation changes, these need
checking:

| Page | Depends on |
|---|---|
| `diagnostics.md` | Every `BRIDGE***` code and its severity |
| `cli-reference.md` | Command flags and exit codes in `src/agentbridge/cli.py` |
| `engine-mapping.md` | The table in `src/agentbridge/mapping/concepts.py` |
| `spec-tools.md` | `_BUILTIN_SHIMS` in the LangGraph emitter |
| `spec-workflow.md` | `_NO_SAMPLING_PARAMS` in `ir/validate.py` |

To regenerate the mapping table from source:

```bash
agentbridge mapping
```

To list every diagnostic code actually emitted:

```bash
grep -rhoE '"BRIDGE[0-9]{3}"' src/ | sort -u
```

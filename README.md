# Adeptus Craftmatica

> A professional command center for miniature painters, hobbyists, collectors, and campaign organizers.

Adeptus Craftmatica is a cross-platform desktop application designed to bring structure, momentum, and satisfaction to creative hobby workflows. Track projects. Organize paints. Manage armies. Plan campaigns. Build shopping lists. Visualize progress — all in one place, fully offline.

Built by a hobbyist, for hobbyists.

---

## 📦 Downloads

| Platform | Format | Notes |
|---|---|---|
| **macOS** | `.dmg` | Drag to Applications, double-click to launch |
| **Windows** | `.zip` | Extract and run `Adeptus Craftmatica.exe` |

Download the latest release from the [Releases page](../../releases).

> **User data** is stored separately from the app and survives updates automatically:
> - macOS: `~/Library/Application Support/AdeptusCraftmatica/`
> - Windows: `%APPDATA%\AdeptusCraftmatica\`

---

## ✨ Feature Overview

### 📊 Dashboard
Two dashboard variants giving you a live overview of your entire hobby life:
- Real-time cross-plugin intelligence and activity feed
- Active project summaries with progress bars
- Quick-action buttons for common tasks
- Fully customizable widget layout (v2)
- Recommended next actions driven by your data

### 📅 Calendar 2.0
A full hobby timeline and planner:
- Today, Week, Month, and Agenda views
- Day-selection side panel with per-day event list
- Manual event creation with priority, category, session type, and duration
- Auto-generated activity events from all connected plugins (purchases, completions, sessions, battles)
- Timezone support with DST toggle, 12h/24h time, and configurable date formats
- Regional and display preferences via the Calendar settings page

### 🛠 Projects 2.0
A premium project tracker built for long-running hobby work:
- Milestone tracking with quantity-based progress
- Hobby session logging (start / stop timer + notes)
- Linked paints, models, armies, and resources
- Progress galleries per project
- Notes, workflow planning, and status management

### 🎨 Paint Studio

**Paint Tracker 2.0** — Card-grid paint inventory with usage logging and smart restocking alerts.

**Paint Schemes 2.0** — Recipe builder with step-by-step painting guides and model linking.

**Chroma Codex 2.0** — Intelligent palette generator. Pick a primary colour and get scientifically-derived complementary, triadic, and analogous recommendations matched against your actual paint collection.

### ⚔ Army & Collection

**Army Builder 2.0** — System-agnostic army list manager with card grid, inline unit builder, and points tracking. Supports Warhammer 40K, AoS, Kill Team, D&D, and custom game systems.

**Model Command 2.0** — Professional miniature collection manager with pipeline view (Backlog → In Progress → Complete), drag-and-drop reordering, squad tracking, and Wall of Shame for long-abandoned models.

### 🎲 Campaign Command 2.0
A full command centre for tabletop RPG and wargame campaigns:
- Supports D&D 5e, Pathfinder 2e, Warhammer 40K, AoS, Necromunda, Kill Team, and custom systems
- Session tracking with notes and outcomes
- Character and faction management
- Battle logging with campaign linkage
- Quest and narrative management

### 🔧 Supplies & Tools

**Tool Tracker 2.0** — Toolkit manager with condition tracking, project linking, and restocking recommendations. Covers nippers, files, brushes, adhesives, and custom tool types.

**Materials Tracker 2.0** — Basing and scenic supplies manager covering static grass, tufts, sand, water effects, and more. Stock tracking with low-stock alerts.

### 🛒 Shopping List
A dedicated hobby shopping list plugin:
- Create and manage multiple named shopping lists
- Collapsible sections (General, project-specific, or custom)
- Add items manually or pull directly from your Paint, Tool, Material, and Miniature inventory
- Mark items as purchased, remove purchased in bulk, or clear all
- Search and category filtering
- Duplicate detection with automatic quantity merging
- Export as Plain Text, CSV, or JSON — copy to clipboard, save to file, or open with your system

---

## ⚡ Core Systems

| System | Description |
|---|---|
| **Plugin Architecture** | Every feature is a self-contained plugin. Enable, disable, or extend independently. |
| **Event Bus** | Decoupled communication between plugins. One purchase auto-logs to the Calendar, Shopping List, and Dashboard simultaneously. |
| **Service Registry** | Plugins expose typed services other plugins can consume safely. |
| **Settings Registry** | Each plugin registers its own settings page into the global Settings dialog. |
| **Theme Engine** | 13 built-in themes including dark defaults, faction-inspired palettes (Ultramarines, Necron Horde, Blood for the Blood God), and user-created themes. Full QSS token system. |
| **Command Palette** | `Ctrl+P` / `Cmd+P` global launcher — navigate, create, and trigger actions from anywhere. |
| **Dashboard Registry** | Plugins register dashboard widgets and stat providers that surface automatically on the Dashboard. |

---

## 🗂 Plugin Reference

| Plugin | Version | Category |
|---|---|---|
| Dashboard | 1.0.0 | Core |
| Dashboard 2.0 | 2.0.0 | Core |
| Paint Tracker | 0.3.0 | Paints |
| Paint Tracker 2.0 | 1.0.0 | Paints |
| Paint Schemes | 0.1.0 | Paints |
| Paint Schemes 2.0 | 2.0.0 | Paints |
| Chroma Codex 2.0 | 2.0.0 | Paints |
| Model Tracker | 0.1.0 | Collection |
| Model Command 2.0 | 2.0.0 | Collection |
| Army Builder | 0.1.0 | Collection |
| Army Builder 2.0 | 1.0.0 | Collection |
| Campaign Tracker | 0.1.0 | Campaigns |
| Campaign Command 2.0 | 2.0.0 | Campaigns |
| Projects | 1.0.0 | Planning |
| Projects 2.0 | 2.0.0 | Planning |
| Calendar | 1.0.0 | Planning |
| Calendar 2.0 | 2.0.0 | Planning |
| Tool Tracker | 1.0.0 | Supplies |
| Tool Tracker 2.0 | 1.0.0 | Supplies |
| Materials Tracker | 1.0.0 | Supplies |
| Materials Tracker 2.0 | 1.0.0 | Supplies |
| Shopping List | 1.0.0 | Supplies |

> v1 plugins are retained for data compatibility. v2 plugins read from the same database tables — upgrading loses nothing.

---

## 🧠 Philosophy

Creative hobbies deserve professional-grade tools.

Most hobby apps focus on isolated features. Adeptus Craftmatica focuses on **workflow** — helping creators stay organized, motivated, and connected to their projects over the long term. The event-driven architecture means every action ripples intelligently across the whole application: finish a model and it logs to your project, fires a calendar entry, and updates your dashboard stats automatically.

The goal is not just tracking collections. The goal is helping people finish things.

---

## 🖥 Tech Stack

| | |
|---|---|
| **Language** | Python 3.13 |
| **UI Framework** | PySide6 (Qt 6.6+) |
| **Database** | SQLite (via Python `sqlite3`) |
| **Architecture** | Modular plugin system with event bus |
| **Styling** | Qt Style Sheets (QSS) with full token theming |
| **Packaging** | PyInstaller — native `.app` on macOS, `.exe` on Windows |
| **CI/CD** | GitHub Actions — builds both platforms automatically on every release tag |

---

## 🚀 Running from Source

**Requirements:** Python 3.13, PySide6

```bash
# Clone the repo
git clone <repo-url>
cd "Adeptus Craftmatica"

# Install dependencies
pip install -r requirements.txt

# Run
python main.py
```

When running from source, `app.db` is created in the project root. All data is stored locally — no cloud accounts required.

---

## 🎨 Themes

13 themes ship with the application, selectable from **Settings → Application → Theme**:

| Theme | Style |
|---|---|
| Dark Default | Clean neutral dark |
| Dark Emerald | Dark with green accents |
| Dark Midnight | Deep blue-black |
| Dark Warm | Dark with warm amber tones |
| Ultramarines | Deep blue, Macragge gold |
| Blood for the Blood God | Deep crimson and bone |
| Necron Horde | Cold green energy, dark metal |
| Seafoam | Soft teal dark |
| Vallejo Silver | Muted silver-grey |

Additional themes can be created and placed in the `themes/` directory as JSON token files.

---

## 🔨 Building a Release

Releases are built with a single script. Both macOS and Windows are handled automatically — you only need to run it once from your Mac.

```bash
python release_mac.py
```

Enter a version number when prompted. The script builds the macOS DMG locally, commits, tags, and pushes. GitHub Actions then automatically builds the Windows release in parallel and attaches both files to the GitHub Release page.

---

## 🚧 Development Status

Active development. Core systems are stable and all plugins operational on both macOS and Windows. Current focus areas:

- UX refinement and visual consistency
- Cross-plugin event integration
- Performance with large collections
- Onboarding and first-run experience
- Additional theme variants
- Plugin customization options

---

## 📌 Vision

Adeptus Craftmatica aims to become the definitive creative workflow platform for miniature hobbyists — combining productivity, collection management, campaign organization, and creative momentum into a single unified, offline-first experience.

---

## 👋 About

Built independently with an obsession for clean workflows, polished UX, and systems that actually support real hobby habits.

If you're into miniature painting, worldbuilding, collecting, campaigns, or long-form creative projects — this is for you.

# Folderwise visual assets

The logo and hero banner were generated with the built-in image generation tool for Folderwise and selected by the project owner. The logo is a transparent raster concept. These illustrations do not depict a separate Folderwise application.

The Obsidian screenshot is an unedited app-window capture from a disposable demonstration vault. Infrastructure, hosts, and addresses are fictional. Obsidian provides the pictured graph and document interface. Cross-project links shown are demo-only; Folderwise currently validates links within each project repository. No financial identifiers or claim records appear.

The three SVG badges contain static, factual project metadata. They do not claim a CI result or publication status.

The notification icon in `_tools/ibridge_assets/folderwise.icns` derives from `folderwise-logo.png`. Transparent pixels below alpha 13 were trimmed, the artwork fitted within a 900-pixel square on a transparent 1024-pixel canvas, then resized for macOS standard/Retina icon sizes. The original artwork is unchanged.

`ibridge-macos-notification.png` is the project owner’s real macOS setup-success notification from the fictional bridge test. It was cropped from `SCR-20261025-prno.png` to remove surrounding desktop space; the logo, message, colors, and notification UI were not altered. It shows setup confirmation, not an error alert.

## iPhone workflow assets (2026-10-25)

Owner-supplied, real-device acceptance captures from the fictional bridge test identified as `20261025-201506-iphone-acceptance`. The source JPEGs are unedited iPhone Mirroring window captures; the Mac error banner is a separate owner capture. Originals remain outside this repository, with their original bytes and permissions. No raw evidence folders, logs or private absolute paths are included.

**Interfaces and evidence:** Obsidian, its Tasks plugin, iPhone Mirroring and macOS provide the pictured interfaces. Folderwise is not a standalone iPhone app. `lab-notes` and `trip-notes`, task wording and records are fictional test data; a displayed `sensitivity: private` is a fixture value. Screenshots establish visible phone or banner state at particular moments. Returned-state labels follow the owner's capture descriptions; they do not independently prove an import or a local Git commit. No image demonstrates selected-note text editing.

**Review and transformations:** Source contact-sheet review covered all 13 phone captures, both Mac banner versions and all existing repository raster assets. Selected images contain fictional task data and device status, with no personal names, addresses, credentials or private filesystem paths observed. No redaction was needed. Screen text, checkboxes, cursor artefacts, errors and source links were not changed. No UI was reconstructed or generated, and no different moments were spliced into a single screen. Crops are separately framed and labelled. Raster output uses lossless, optimized RGB PNG; original screenshot pixels are pasted at native scale, with display resizing left to the reader. Compositions use cream, teal and charcoal derived from the established branding, Arial typography, and external labels drawn with Pillow. No new generative artwork was used.

| Asset | Kind and sources | Transformation and purpose |
| --- | --- | --- |
| `ibridge-iphone-dashboard.png` | Derivative composition; `01-dashboard-baseline-open-top.jpg` plus existing `folderwise-logo.png` | 560 × 1360. Full 490 × 1075 capture pasted at (35, 190); original logo's transparent padding trimmed and logo resized to fit 64 × 64. New background, heading and footer outside the capture. Chosen for its clear All projects heading and open tasks from both demo projects. Baseline state, before testing; not proof of an import. |
| `ibridge-task-cycle.png` | Derivative sequence; captures `04-csv-complete-tapped-on-iphone-before-sync.jpg`, `07-csv-source-backlog-empty-after-completion.jpg`, `09-reopen-md-and-csv-tapped-before-sync.jpg`, `10-csv-source-backlog-reopened-row-returned.jpg` | 560 × 1555. Four labelled excerpts, in that order. Crop boxes (left, top, right, bottom; right/bottom excluded): (30, 810, 465, 958), (30, 680, 465, 920), (30, 385, 465, 535), (30, 715, 465, 970). Native-size excerpts on black cards with external labels. Chosen to compare before-sync dashboard actions with returned source backlog states. **Two different CSV demo tasks**, one completed and another reopened; not a single task's entire lifecycle. |
| `ibridge-task-rename.png` | Derivative composition; `13-rename-returned-on-iphone.jpg` | 560 × 620. Crop (22, 190, 465, 580), pasted at (58, 135) without resizing; cream background and external labels. Shows the generated view's opt-in instructions, renamed control task and retained source link. Returned phone state; commit evidence is separate. |
| `ibridge-macos-error.png` | Authentic capture derivative; `01-folderwise-error-banner.trimmed.png`, itself cropped by the owner from `01-folderwise-error-banner.original.png` | 360 × 93. Lossless PNG optimization of the owner's existing crop, without changing pixels or notification wording. Actual needs-attention banner, not setup success. Used in recovery guidance, not as evidence that recovery completed. |
| `ibridge-workflow.svg` | Code-native illustration, no screenshot | 560 × 960. Authored SVG typography, cards and arrows explain selected exports, supported imports, separate vault, Obsidian interface and Mac-local commits. A conceptual workflow, not a capture or a hosted service. Opt-in details and validation constraints are explained in the surrounding documentation. |

### Selection notes

- `01` was preferred to `02-dashboard-baseline-both-projects.jpg`: both show the two projects, but `01` retains a clear dashboard title without the scrolling header overlap.
- `03-md-complete-tapped-on-iphone-before-sync.jpg`, `05-dashboard-after-background-sync-completed.jpg`, `06-md-source-note-returned-from-mac.jpg` and `08-completed-view-before-reopen.jpg` provide useful supporting state but would duplicate the chosen CSV sequence. The returned Markdown source (`06`) shows task completion, not free-form note editing.
- `11-dashboard-after-reopen-sync.jpg` has a rendering glitch and is excluded from promotional use.
- `12-rejected-edit-restored-view-on-iphone.jpg` is supporting recovery state; it is omitted to avoid another near-identical task-view image. The actual error banner plus written recovery steps supplies the useful troubleshooting context.
- The existing hero and logo remain the brand assets. The desktop graph remains available in the README's expandable desktop example. The existing setup-success notification, Login Items screenshot and macOS background-activity notice remain in their relevant setup sections; none is relabelled as an error.

### Existing assets retained

`obsidian-login-items.png` and `obsidian-background-activity-notice.png` are existing authentic macOS interface captures documenting helper registration and the system's own background-activity notice. They are unchanged in this work. As with `ibridge-macos-notification.png`, neither establishes a successful phone import. The original branding, desktop demo and badge provenance above continues to apply.

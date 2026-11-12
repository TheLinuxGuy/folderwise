---
title: Acceptance 0.2.0 Markdown fixtures
doc_type: plan
status: active
sensitivity: private
owner: human
created: 2026-10-26
updated: 2026-10-28
updated_by: human
last_verified: null
review_every: 90d
tags: []
summary: Fictional task fixtures for the 0.2.0 iPhone acceptance run
---
# Acceptance 0.2.0 Markdown fixtures

<!-- byline:start -->
> **Status:** active · **Updated:** 2026-10-28 by human
<!-- byline:end -->

## Goal

Fictional tasks for the 0.2.0 real-iPhone acceptance run. Every task id (AT-...) maps to one case.

## Basic and metadata

- [ ] AT-B01 complete me on the phone
- [ ] RN-AT-B02 reopen me on the phone
- [ ] AT-B03 add due and start dates on phone 🛫 2026-12-01 📅 2026-12-20 🔺
- [-] AT-B04 add scheduled and priority on phone ⏫ ⏳ 2026-12-15 ❌ 2026-10-26
- [ ] RN-AT-B05 has existing metadata 📅 2026-12-01 🔼 #lab/tag
- [ ] AT-B06 unicode café 日本語 🎉 #lab/ünï [ext link](https://example.com/at) 🆔 atb06 🔽
- [ ] AT-B07 block id task ⏬ ^atb07blk
- [ ] AT-B08 dependency target 🆔 atb08
- [x] AT-B09 dependsPART-FINAL- on target ⛔ atb08
- [ ] AT-B10 edit wording only 📅 2026-12-06 #keep ⛔ atb08

## Statuses

- [x] AT-S01 in progress task
- [ ] AT-S02 cancelled task
- [x] AT-S03 cancel me from phone
- [ ] AT-S04 custom status target

## Hierarchy

- [ ] AT-H01 parent
  - [x] AT-H01a child
    - [ ] AT-H01a1 grandchild
  - [ ] AT-H01b child
- [ ] AT-H02 tabbed parent
	- [ ] AT-H02a tab child
		- [x] AT-H02a1 tab grandchild
1. [ ] AT-H03 numbered parent
   1. [x] AT-H03a numbered child
- plain list parent for non-task
  - [x] AT-H04 child of a plain item
  continuation text under the plain list
> - [x] AT-H05 quoted task
> > - [x] AT-H06 doubly quoted task
> [!note] callout
> - [x] AT-H07 callout task
- [x] AT-H08 parent A
  - [x] AT-H08x same child title
- [ ] AT-H09 parent B
  - [x] AT-H09x same child title
- [x] AT-H10 first sibling
- [ ] AT-H11 second sibling

```markdown
- [ ] AT-F01 fenced example is not a task
```

> ```
> - [ ] AT-F02 quoted fenced example is not a task
> ```

## Recurrence and completion actions

- [ ] AT-R01 daily recurrence 🔁 every day 📅 2026-11-03
- [x] AT-R01 daily recurrence 🔁 every day 📅 2026-11-02
- [ ] AT-R02 weekly recurrence 🔁 every week 🛫 2026-11-06 📅 2026-11-10
- [x] AT-R02 weekly recurrence 🔁 every week 🛫 2026-10-30 📅 2026-11-03
- [ ] AT-R03 monthly recurrence 🔁 every month 📅 2026-12-04
- [x] AT-R03 monthly recurrence 🔁 every month 📅 2026-11-04
- [ ] AT-R04 when done recurrence 🔁 every week when done 📅 2026-11-02
- [x] AT-R04 when done recurrence 🔁 every week when done 📅 2026-11-05
- [ ] AT-R05 undated recurrence 🔁 every day
- [x] AT-R05 undated recurrence 🔁 every day
- [x] AT-D02 keep on completion 🏁 keep
- [ ] AT-D03 recurring and delete 🔁 every day 🏁 delete 📅 2026-11-08

## Concurrency and conflicts

- [ ] AT-C01 concurrent different fields 📅 2026-12-12 🔼
- [ ] AT-C02 concurrent same field 📅 2026-12-20
- [ ] AT-C03 source changes during sync 📅 2026-12-30
- [ ] AT-C04 offline edit task
- [ ] AT-C05 stale view task

## Reordering target

- [ ] AT-X01 reorder one
- [ ] AT-X02 reorder two
- [ ] AT-X03 reorder three

## Change Log

<!-- changelog:start -->
| When | By | Summary |
|------|----|---------|
| 2026-10-28 20:31 PDT | human | Toggle tasks via Obsidian iCloud bridge (import 5539afd373cc) |
| 2026-10-26 22:40 PDT | human | Update task fields and occurrences via Obsidian iCloud bridge (import 94341c750d43) |
| 2026-10-26 21:54 PDT | claude/sonnet-5.5 | Mac due edit on C02 for isolated same-field test |
| 2026-10-26 21:52 PDT | human | Update task fields and occurrences via Obsidian iCloud bridge (import 85b29a6e2f8c) |
| 2026-10-26 09:35 PDT | human | Update task fields and occurrences via Obsidian iCloud bridge (import 12f957f78483) |
| 2026-10-26 09:30 PDT | human | Update task fields and occurrences via Obsidian iCloud bridge (import 3e3bbe82e61c) |
| 2026-10-26 02:45 PDT | claude/sonnet-5.5 | Mac due edit on C02 vs phone due edit |
| 2026-10-26 02:32 PDT | human | Update task fields and occurrences via Obsidian iCloud bridge (import 4d987d41017b) |
| 2026-10-26 02:30 PDT | claude/sonnet-5.5 | Mac priority edit on C01 while phone due edit pending |
| 2026-10-26 02:25 PDT | human | Update task fields and occurrences via Obsidian iCloud bridge (import ece7118ac97a) |
<!-- changelog:end -->

"""Source of truth for the reviewer test sets. Run it to regenerate evals/data/reviewer/*.jsonl.

Each item is a short document of one content type with hand-labeled rule violations. The labels
cover both deterministic rules and judgment rules, so the sets measure the whole reviewer: the
checks and the model. Clean items have no labels and measure false positives. KB items use the
KB subtypes (task, concept, troubleshooting, walkthrough, and the learning types).
"""

import json
from pathlib import Path

FENCE = "```"
EMPTY = "No changes in this release."
RN_HEADINGS = [
    "New features", "Improvements", "Bug fixes", "Security updates", "API and developer changes",
    "Deprecations and removals",
]


def release(title: str, sections: dict[str, str]) -> str:
    """A release note with all six headings. Sections not given read 'No changes in this release.'"""
    parts = [f"# {title}\n"]
    for heading in RN_HEADINGS:
        parts.append(f"## {heading}\n\n{sections.get(heading, EMPTY)}\n")
    return "\n".join(parts)


def api_page(
    title: str,
    intro: str,
    endpoint: str,
    table: str,
    body: str,
    curl: str,
    language: str | None = 'client.call()',
    success: str | None = '{"id": "n_1"}',
    error: str | None = '{"error": {"code": "not_found", "message": "No item has this ID."}}',
) -> str:
    parts = [f"# {title}\n", f"{intro}\n", f"`{endpoint}`\n", table, f"{body}\n", f"{FENCE}bash\n{curl}\n{FENCE}\n"]
    if language:
        parts.append(f"{FENCE}python\n{language}\n{FENCE}\n")
    if success:
        parts.append(f"A successful call returns:\n\n{FENCE}json\n{success}\n{FENCE}\n")
    if error:
        parts.append(f"An error returns:\n\n{FENCE}json\n{error}\n{FENCE}\n")
    return "\n".join(parts)


TABLE_ID = (
    "| Parameter | Type | Required or optional | Description |\n|---|---|---|---|\n"
    "| `id` | string | Required | The ID of the item. |\n"
)

KB = [
    dict(
        id="kb-r01", content_type="kb_task",
        violations=["heading_case", "first_person", "kb_numbered_steps", "kb_task_sections", "conclusion_first"],
        notes="The intro sells the feature instead of stating the goal, and there are no prerequisites or verification.",
        text=(
            "# How To Share A Notebook\n\n"
            "Notebooks are a core part of Fernbook, and we made sharing simple.\n\n"
            "## Steps\n\n- Open the notebook.\n- Click **Share**.\n- Enter the email address of a teammate.\n"
        ),
    ),
    dict(
        id="kb-r02", content_type="kb_task",
        violations=["one_term_per_concept"],
        notes="Mixes 'sign-in' with 'log in' and 'login' for the same action.",
        text=(
            "# Reset your password\n\n"
            "Reset your password when you forget it or when an admin asks you to.\n\n"
            "## Before you begin\n\nYou need access to the email address on your account.\n\n"
            "## Steps\n\n"
            "1. On the sign-in page, click **Forgot password**.\n"
            "2. Open the reset email and follow the link within 2 hours.\n"
            "3. Log in with the new password.\n\n"
            "## Verify the change\n\n"
            "Fernbook opens your home page. If the link expires, request a new one from the login page.\n"
        ),
    ),
    dict(
        id="kb-r03", content_type="kb_task",
        violations=["oxford_comma", "semicolons", "ui_bold", "monospace"],
        notes="UI names are not bold, and the command is not in backticks.",
        text=(
            "# Connect Fernbook to your identity provider\n\n"
            "Connect Fernbook to your identity provider so your team signs in with one account.\n\n"
            "## Prerequisites\n\nYou need the Owner role, a metadata URL, an entity ID and a certificate.\n\n"
            "## Procedure\n\n"
            "1. In Settings, open the Single sign-on tab; paste the metadata URL.\n"
            "2. Click Save.\n"
            "3. Run fernbook-cli verify-sso to test the connection.\n\n"
            "## Verify the connection\n\nThe tab shows a green check mark.\n"
        ),
    ),
    dict(
        id="kb-r04", content_type="kb_task",
        violations=[],
        text=(
            "# Pin a note\n\n"
            "Pin a note to keep it at the top of its notebook.\n\n"
            "## Before you begin\n\nYou need edit access to the notebook.\n\n"
            "## Steps\n\n1. Open the note.\n2. Click **More** > **Pin to top**.\n\n"
            "## Verify the result\n\nThe note moves to the top of the list. To unpin it, click **More** > **Unpin**.\n"
        ),
    ),
    dict(
        id="kb-r05", content_type="kb_concept",
        violations=["passive_voice", "all_caps", "kb_concept_sections"],
        notes="The opening sentence has 27 words, which the conceptual cap of 28 allows.",
        text=(
            "# How sync works\n\n"
            "Kestrel Sync keeps every device on the same version of your files, and it resolves conflicts by keeping "
            "both copies until you pick the one to keep.\n\n"
            "## Core concepts\n\n"
            "Each change is recorded by the sync service as an event. NEVER edit the event log by hand.\n\n"
            "## Architecture\n\n![Sync architecture](sync.png)\n"
        ),
    ),
    dict(
        id="kb-r06", content_type="kb_concept",
        violations=[],
        text=(
            "# Workspaces and notebooks\n\n"
            "A workspace holds the notebooks, members, and settings of one team, and every notebook belongs to "
            "exactly one workspace at a time.\n\n"
            "## Core concepts\n\n"
            "- **Workspace** – The container for the notebooks and members of a team.\n"
            "- **Notebook** – A collection of notes with its own sharing settings.\n\n"
            f"## Architecture\n\n{FENCE}mermaid\ngraph TD\n  Workspace --> Notebook\n{FENCE}\n\n"
            "## Related tasks\n\n- [Create a workspace](create-workspace.md)\n- [Share a notebook](share-notebook.md)\n"
        ),
    ),
    dict(
        id="kb-r07", content_type="kb_troubleshooting",
        violations=["back_reference", "hedging", "ts_environment"],
        notes="The issue depends on macOS 15, but the guide has no environment or scope section.",
        text=(
            "# Sync stops on a metered connection\n\n"
            "## Symptom\n\nOn macOS 15, the tray icon turns gray, and files stop syncing.\n\n"
            "## Cause\n\nYour operating system marks the connection as metered. "
            "As mentioned above, Kestrel Sync pauses on metered connections.\n\n"
            "## Resolution\n\n"
            "You might want to turn off **Pause on metered connections** in **Settings** > **Network**.\n"
        ),
    ),
    dict(
        id="kb-r08", content_type="kb_troubleshooting",
        violations=["ts_sections", "first_person"],
        text=(
            "# Export fails with error E4012\n\n"
            "## Resolution\n\nClear the export cache in **Settings** > **Storage**, then export again.\n\n"
            "## Symptom\n\nThe export stops at 90 percent and shows error E4012.\n\n"
            "## Cause\n\nOur export service rejects a cache that is older than 30 days.\n"
        ),
    ),
    dict(
        id="kb-r09", content_type="walkthrough",
        violations=["walk_ui_verbs", "walk_step_density"],
        notes="Step 2 gives one click its own number, which the next step could absorb.",
        text=(
            "# Tour of the board view\n\n"
            "Learn the board view.\n\n"
            "1. Press **New board**.\n"
            "2. Click the **Name** field.\n"
            "3. Type `Roadmap` in the **Name** field.\n"
            "4. Click **Create**.\n"
        ),
    ),
    dict(
        id="kb-r10", content_type="concept_guide",
        violations=["learn_no_procedures"],
        text=(
            "# How permissions flow\n\n"
            "Permissions flow down from a workspace to its notebooks, and a notebook can only narrow the access "
            "that its workspace grants.\n\n"
            "## Core ideas\n\n"
            "- **Inheritance** – A notebook starts with the permissions of its workspace.\n"
            "- **Narrowing** – A notebook can remove access, but it cannot add access.\n\n"
            "## Try it\n\n1. Open a notebook.\n2. Click **Share**.\n"
        ),
    ),
    dict(
        id="kb-r11", content_type="tutorial",
        violations=["learn_tutorial_sections", "learn_measurable_objectives"],
        notes="No learning objectives at the start and no verification at the end.",
        text=(
            "# Tutorial: build your first board\n\n"
            "In this tutorial, you build a board.\n\n"
            "## Concepts\n\nA board holds cards in columns.\n\n"
            "## Steps\n\n1. Click **New board**.\n2. Enter `Roadmap` in the **Name** field and click **Create**.\n"
        ),
    ),
    dict(
        id="kb-r12", content_type="quickstart",
        violations=["learn_quickstart_no_concepts"],
        notes="The second paragraph explains the pipeline instead of getting the reader to a result.",
        text=(
            "# Quickstart: send your first event\n\n"
            "Send your first event to Orbitly.\n\n"
            "Orbitly is an event platform. Events flow through a pipeline of collectors, processors, and sinks, "
            "and each stage can transform, enrich, or drop the event.\n\n"
            "1. Copy your API key from **Settings** > **API keys**.\n"
            "2. Run the sample command with your key.\n"
        ),
    ),
]

RELEASE = [
    dict(
        id="rn-r01",
        violations=["contractions", "preamble", "rn_sections", "rn_engineering_framing", "rn_capability_first"],
        text=(
            "# What's new in Fernbook 2.6\n\n"
            "We're excited to share this month's updates!\n\n"
            "## New\n\n- We added search inside attachments.\n\n"
            "## Fixed\n\n- Tags save again when you rename them, which didn't work before.\n"
        ),
    ),
    dict(
        id="rn-r02",
        violations=["rn_deprecation_callout", "rn_deprecation_fields"],
        notes="The removal sits in a plain bullet, with no date, impact, or migration path.",
        text=release("Orbitly API 3.0 release notes", {
            "New features": "- Webhooks now retry failed deliveries up to 5 times.",
            "Deprecations and removals": "- The `page` parameter of `GET /v3/events` is removed.",
        }),
    ),
    dict(
        id="rn-r03",
        violations=["rn_capability_first", "monospace", "acronyms"],
        notes="Describes internal work and a code path, and leaves NPE and MIME unexplained.",
        text=release("Fernbook 2.6 release notes", {
            "Improvements": (
                "- The sync queue now runs on three worker modules.\n"
                "- Notebooks with over 1,000 notes open twice as fast."
            ),
            "Bug fixes": "- Resolved an NPE in AttachmentUploader when the MIME type was empty.",
        }),
    ),
    dict(
        id="rn-r04",
        violations=["sentence_length", "passive_voice", "oxford_comma", "hedging"],
        text=release("Kestrel Sync 4.2 release notes", {
            "New features": (
                "- Selective sync is now available on every plan, and folders can be excluded by an admin from the "
                "web console without any change to the desktop apps.\n- Sync history now shows uploads, downloads and deletions."
            ),
            "Bug fixes": "- Large files probably resume faster after a dropped connection.",
        }),
    ),
    dict(
        id="rn-r05",
        violations=[],
        text=release("Fernbook 2.5 release notes", {
            "New features": "- You can now export a notebook as Markdown from **File** > **Export**.",
            "Bug fixes": "- Tags now save when you rename a notebook.",
            "Security updates": "- Sessions now expire after 12 hours of inactivity.",
        }),
    ),
    dict(
        id="rn-r06",
        violations=[],
        text=release("Orbitly API 3.1 release notes", {
            "API and developer changes": "- `GET /v3/events` now responds up to 40 percent faster for large accounts.",
            "Deprecations and removals": (
                "> **Warning:** The `limit` parameter of `GET /v3/events` stops working on 2027-01-31.\n"
                "> - **Feature name** – The `limit` parameter.\n"
                "> - **End-of-life date** – 2027-01-31.\n"
                "> - **Impact or reason** – Requests that send `limit` fail with `400`, because cursor pagination "
                "replaces page sizes.\n"
                "> - **Migration path** – Switch to the `cursor` parameter. See "
                "[the pagination guide](https://example.com/pagination)."
            ),
        }),
    ),
    dict(
        id="rn-r07",
        violations=["link_text", "numerals", "ui_bold"],
        notes="'twelve' must be a numeral, and the Pin menu name is not bold.",
        text=release("Quillpad 1.8 release notes", {
            "New features": (
                "- You can now pin up to twelve notes per notebook. Open the Pin menu to try it.\n"
                "- Read the full details [here](https://example.com/blog)."
            ),
        }),
    ),
    dict(
        id="rn-r08",
        violations=["em_dash", "back_reference", "rn_sections"],
        notes="Bug fixes comes before New features.",
        text=(
            "# Tessellate 5.0 release notes\n\n"
            "## Bug fixes\n\n- Both export tools are faster. The former works with every format, and the latter "
            "works with PNG and JPG only.\n\n"
            "## New features\n\n- Batch export -- export up to 50 images in one step.\n\n"
            "## Improvements\n\nNo changes in this release.\n\n"
            "## Security updates\n\nNo changes in this release.\n\n"
            "## API and developer changes\n\nNo changes in this release.\n\n"
            "## Deprecations and removals\n\nNo changes in this release.\n"
        ),
    ),
]

MICROCOPY = [
    dict(
        id="ui-r01",
        violations=["preamble", "ui_case", "ui_error_two_part"],
        notes="The error names the problem but offers no next step.",
        text="# Export dialog\n\ntitle: Export your notebook\nbutton: Export Now\nerror: Oops! You entered an invalid file name.\n",
    ),
    dict(
        id="ui-r02",
        violations=["link_text", "ui_case"],
        text=(
            "# Tags\n\ntitle: Delete This Tag?\n"
            "empty_state: You have no tags yet. Create a tag to group related notes.\n"
            "tooltip: Click here to learn about sharing settings\n"
        ),
    ),
    dict(
        id="ui-r03",
        violations=["sentence_length", "first_person"],
        text=(
            "# Setup wizard\n\nbutton: Save and continue\n"
            "error: We couldn't reach the server, so check your connection and then try again in a few minutes.\n"
            "toast: Your changes are saved.\n"
        ),
    ),
    dict(
        id="ui-r04",
        violations=["all_caps", "ui_error_no_why", "semicolons"],
        text="# Upload\n\nbutton: Cancel\nerror: ERROR: Upload failed because the file is too big; try again.\n",
    ),
    dict(
        id="ui-r05",
        violations=["ampersand", "second_person", "hedging"],
        text=(
            "# Notebook form\n\nlabel: Name & description\n"
            "tooltip: The user can perhaps add a description later.\nplaceholder: Search notes\n"
        ),
    ),
    dict(
        id="ui-r06",
        violations=[],
        text=(
            "# Export\n\nbutton: Export notebook\n"
            "error: Couldn't save your file. Check your connection and try again.\n"
            "empty_state: No exports yet. Export a notebook to see it here.\n"
            "tooltip: Exports include attachments up to 25 MB each.\n"
        ),
    ),
    dict(
        id="ui-r07",
        path="locales/en.json",
        violations=[],
        notes="Top-level navigation may use Title Case.",
        text=json.dumps({
            "nav": {"settings": "Account Settings"},
            "share": {
                "button": "Share notebook",
                "error_no_access": "You don't have access to this notebook. Ask the owner to share it.",
                "empty_state": "No one has access yet. Share the notebook to invite your team.",
            },
        }, indent=2) + "\n",
    ),
    dict(
        id="ui-r08",
        violations=["em_dash", "passive_voice", "one_term_per_concept"],
        notes="'Log in' and 'sign-in' name the same action.",
        text=(
            "# Sign-in screen\n\nbutton: Log in\nerror: Your sign-in failed — check your password.\n"
            "toast: The invite was sent by your workspace owner.\n"
        ),
    ),
]

API = [
    dict(
        id="api-r01",
        violations=[
            "heading_case", "contractions", "api_endpoint", "api_params_table", "api_code_samples",
            "api_response_schemas",
        ],
        text="# Delete A Single Note\n\nThis endpoint deletes a note. It's permanent.\n\nThe note ID goes in the path.\n",
    ),
    dict(
        id="api-r02",
        violations=["api_params_table", "api_required_marker"],
        text=api_page(
            "List events", "List the events in an account.", "GET /v3/events",
            "| Name | Type | Required | Description |\n|---|---|---|---|\n| `limit` | integer | No | Events per page, up to 200. |\n",
            "An invalid key returns `401`.",
            'curl -H "Authorization: Bearer <TOKEN>" https://api.example.com/v3/events',
            language="client.events.list(limit=50)",
        ),
    ),
    dict(
        id="api-r03",
        violations=["api_endpoint", "api_masked_tokens", "one_term_per_concept"],
        notes="The prose calls the resource a 'hook' and the page title calls it a 'webhook'.",
        text=api_page(
            "Create a webhook", "Create a webhook to receive events at your own URL.", "POST /v3/webhooks",
            TABLE_ID.replace("`id` | string", "`url` | string").replace("The ID of the item.", "The URL that receives events."),
            "You can also call `post /v3/webhooks` from the SDK. The call returns the new hook.",
            'curl -X POST -H "Authorization: Bearer sk_live_51abc" https://api.example.com/v3/webhooks',
            language='client.webhooks.create(url="https://hooks.example.com")',
        ),
    ),
    dict(
        id="api-r04",
        violations=["filler", "sentence_length", "back_reference", "latin_abbrev"],
        text=api_page(
            "Get a note", "Get one note by its ID.", "GET /v2/notes/{id}", TABLE_ID,
            "Please note that the response contains the `title`, `body`, and `updated_at` fields of the note, and an "
            "archived note also has an `archived` flag. The code mentioned above also covers deleted notes, i.e. notes "
            "in the trash.",
            'curl -H "Authorization: Bearer <TOKEN>" https://api.example.com/v2/notes/n_123',
            language='client.notes.get("n_123")',
        ),
    ),
    dict(
        id="api-r05",
        violations=[],
        text=api_page(
            "Delete a webhook", "Delete a webhook to stop event deliveries to its URL.", "DELETE /v3/webhooks/{id}",
            TABLE_ID, "A successful call returns `204` with an empty body. An unknown ID returns `404`.",
            'curl -X DELETE -H "Authorization: Bearer <TOKEN>" https://api.example.com/v3/webhooks/wh_123',
            language='client.webhooks.delete("wh_123")', success='{"deleted": true}',
        ),
    ),
    dict(
        id="api-r06",
        violations=[],
        text=api_page(
            "List notes", "List the notes in a workspace, newest first.", "GET /v2/notes",
            "| Parameter | Type | Required or optional | Description |\n|---|---|---|---|\n"
            "| `workspace_id` | string | Required | The workspace to list. |\n"
            "| `limit` | integer | Optional | Notes per page, from 1 to 100. Defaults to 20. |\n",
            "Each note has an `id`, a `title`, and an `updated_at` timestamp.",
            'curl -H "Authorization: Bearer <TOKEN>" "https://api.example.com/v2/notes?workspace_id=ws_1"',
            language='client.notes.list(workspace_id="ws_1")',
            success='{"notes": [{"id": "n_1", "title": "Plan", "updated_at": "2026-10-01T09:00:00Z"}], "next_cursor": null}',
        ),
    ),
    dict(
        id="api-r07",
        violations=["second_person", "hedging", "api_response_schemas"],
        notes="The page shows no JSON error schema.",
        text=api_page(
            "Rotate an API key", "Rotate a key to replace it without downtime.", "POST /v2/keys/{id}/rotate", TABLE_ID,
            "The response returns the new key in a `key` field. "
            "The developer should probably store the new key before the grace period ends.",
            'curl -X POST -H "Authorization: Bearer <TOKEN>" https://api.example.com/v2/keys/k_1/rotate',
            language='client.keys.rotate("k_1")', success='{"key": "<NEW_KEY>"}', error=None,
        ),
    ),
    dict(
        id="api-r08",
        violations=["monospace", "numerals", "api_code_samples"],
        notes="'Authorization header' needs backticks, 'fifteen' must be a numeral, and only cURL is shown.",
        text=api_page(
            "Upload an attachment", "Upload a file and attach it to a note. Send your key in the Authorization header.",
            "POST /v2/notes/{id}/attachments", TABLE_ID,
            "Files over 25 MB return `413`. You can attach up to fifteen files to one note.",
            'curl -F "file=@diagram.png" -H "Authorization: Bearer <TOKEN>" https://api.example.com/v2/notes/n_1/attachments',
            language=None,
        ),
    ),
]

GTM_SECTIONS = [
    ("Target persona and pain point", "Operations leads at agencies lose hours each week chasing status across tools."),
    ("Value proposition", "Fernbook Boards puts every project status on one board that updates itself."),
    ("Technical capabilities and scope", "Boards sync with notebooks in real time. The launch covers web and desktop."),
    ("Known limitations and edge cases", "Mobile apps show boards as read-only until the next release."),
    ("Competitive differentiators", "Boards link straight to the notes behind each card, so context travels with status."),
]


def brief(meta: str | None, sections: list[tuple[str, str]], title: str = "Fernbook Boards launch brief") -> str:
    parts = [f"# {title}\n"]
    if meta:
        parts.append(f"{meta}\n")
    parts += [f"## {h}\n\n{b}\n" for h, b in sections]
    return "\n".join(parts)


GTM = [
    dict(id="gtm-r01", violations=[], text=brief("Internal codename: Project Kite", GTM_SECTIONS)),
    dict(
        id="gtm-r02", violations=[],
        notes="First person and a semicolon are allowed in a GTM brief.",
        text=brief(None, GTM_SECTIONS[:1] + [(
            "Value proposition",
            "We give agencies one board for every project; status updates itself as notes change.",
        )] + GTM_SECTIONS[2:]),
    ),
    dict(
        id="gtm-r03", violations=["gtm_sections", "gtm_codename"],
        notes="The value proposition comes last, and the codename leaks into the body.",
        text=brief(
            "Internal codename: Project Kite",
            [GTM_SECTIONS[0], GTM_SECTIONS[2], GTM_SECTIONS[3], GTM_SECTIONS[4],
             ("Value proposition", "Project Kite puts every project status on one board.")],
        ),
    ),
    dict(
        id="gtm-r04", violations=["gtm_sections", "hedging", "ampersand"],
        notes="The brief has no known limitations section.",
        text=brief(None, [
            GTM_SECTIONS[0],
            ("Value proposition", "Fernbook Boards perhaps saves agencies time & effort every week."),
            GTM_SECTIONS[2], GTM_SECTIONS[4],
        ]),
    ),
    dict(
        id="gtm-r05", violations=["gtm_codename"],
        notes="The codename line sits below the opening paragraph instead of at the top.",
        text=(
            "# Fernbook Boards launch brief\n\nThis brief hands the Boards launch to sales and support.\n\n"
            "Internal codename: Project Kite\n\n" + "\n".join(f"## {h}\n\n{b}\n" for h, b in GTM_SECTIONS)
        ),
    ),
    dict(
        id="gtm-r06", violations=["sentence_length", "citations"],
        text=brief("Internal codename: Project Kite", [GTM_SECTIONS[0], (
            "Value proposition",
            "Agencies that adopt a single status board report fewer missed deadlines, faster client updates, and "
            "less time in status meetings than agencies that track work across several tools.[^1]",
        )] + GTM_SECTIONS[2:]),
    ),
]

SETS = {"kb_article": KB, "release_note": RELEASE, "ui_microcopy": MICROCOPY, "api_doc": API, "gtm_brief": GTM}


def main() -> None:
    out_dir = Path(__file__).resolve().parents[1] / "data" / "reviewer"
    out_dir.mkdir(parents=True, exist_ok=True)
    for family, items in SETS.items():
        with open(out_dir / f"{family}.jsonl", "w", encoding="utf-8") as fh:
            for item in items:
                record = {"id": item["id"], "content_type": item.get("content_type", family)}
                record.update({k: v for k, v in item.items() if k not in ("id", "content_type")})
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"wrote {len(items)} items to {family}.jsonl")


if __name__ == "__main__":
    main()

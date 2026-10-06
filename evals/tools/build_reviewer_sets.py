"""Source of truth for the reviewer test sets. Run it to regenerate evals/data/reviewer/*.jsonl.

Each item is a short document of one content type with hand-labeled rule violations. The labels
cover both deterministic rules and judgment rules, so the sets measure the whole reviewer: the
checks and the model. Clean items have no labels and measure false positives.
"""

import json
from pathlib import Path

FENCE = "```"

KB = [
    dict(
        id="kb-r01",
        violations=["heading_case", "contractions", "kb_numbered_steps", "kb_outcome_first"],
        notes="Opens with a general statement instead of the outcome.",
        text=(
            "# How To Share A Notebook\n\n"
            "Notebooks are a core part of Fernbook. You'll find sharing options in two places.\n\n"
            "- Open the notebook.\n- Click **Share**.\n- Enter your teammate's email address.\n"
        ),
    ),
    dict(
        id="kb-r02",
        violations=["one_term_per_concept"],
        notes="Mixes 'sign-in' with 'log in' and 'login' for the same action.",
        text=(
            "# Reset your password\n\n"
            "Reset your password when you forget it or when an admin asks you to.\n\n"
            "1. On the sign-in page, click **Forgot password**.\n"
            "2. Enter the email address for your account.\n"
            "3. Open the reset email and follow the link within 2 hours.\n"
            "4. Log in with the new password.\n\n"
            "When the new password works, Fernbook opens your home page. "
            "If the link expires, request a new one from the login page.\n"
        ),
    ),
    dict(
        id="kb-r03",
        violations=["passive_voice", "back_reference", "hedging", "kb_troubleshooting_shape"],
        notes="The troubleshooting page never says how to confirm the fix.",
        text=(
            "# Sync stops on a metered connection\n\n"
            "Kestrel Sync pauses itself on metered connections to save data.\n\n"
            "## Symptom\n\nThe tray icon turns gray, and files stop syncing.\n\n"
            "## Cause\n\nThe connection is flagged by your operating system as metered. "
            "As mentioned above, Kestrel Sync pauses on such connections.\n\n"
            "## Fix\n\nYou might want to turn off **Pause on metered connections** in **Settings** > **Network**.\n"
        ),
    ),
    dict(
        id="kb-r04",
        violations=["oxford_comma", "ui_bold", "monospace"],
        notes="UI names are not bold, and the command is not in backticks.",
        text=(
            "# Connect Fernbook to your identity provider\n\n"
            "Connect Fernbook to your identity provider so your team signs in with one account.\n\n"
            "1. In Settings, open the Single sign-on tab.\n"
            "2. Paste the metadata URL, the entity ID and the certificate.\n"
            "3. Click Save.\n"
            "4. Run fernbook-cli verify-sso to test the connection.\n\n"
            "When the test passes, the tab shows a green check mark.\n"
        ),
    ),
    dict(
        id="kb-r05",
        violations=["preamble", "filler", "second_person", "sentence_length", "kb_outcome_first"],
        notes="Opens with chatter instead of the outcome.",
        text=(
            "# Archive a workspace\n\n"
            "Welcome aboard! Archiving is one of our most requested features. "
            "Please note that the user must be a workspace owner in order to archive a workspace, and archived "
            "workspaces stay readable for every member until an owner restores them or deletes them for good.\n\n"
            "1. Open **Workspace settings**.\n2. Click **Archive workspace**.\n"
        ),
    ),
    dict(
        id="kb-r06",
        violations=["bold_leadin", "em_dash", "latin_abbrev", "ampersand"],
        text=(
            "# Export formats\n\n"
            "Choose an export format before you export a notebook.\n\n"
            "- **PDF:** A fixed layout for printing — best for sharing.\n"
            "- **Markdown** – Plain text with formatting marks (e.g. headings and code).\n"
            "- **HTML** – A web page with images & styles inline.\n"
        ),
    ),
    dict(
        id="kb-r07",
        violations=[],
        text=(
            "# Pin a note\n\n"
            "Pin a note to keep it at the top of its notebook.\n\n"
            "1. Open the note.\n2. Click **More** > **Pin to top**.\n\n"
            "The note moves to the top of the list. To unpin it, click **More** > **Unpin**.\n"
        ),
    ),
    dict(
        id="kb-r08",
        violations=[],
        text=(
            "# Recover a deleted note\n\n"
            "Recover a deleted note from the trash within 30 days of deleting it.\n\n"
            "1. In the sidebar, click **Trash**.\n2. Select the note.\n3. Click **Restore**.\n\n"
            "The note returns to its original notebook. After 30 days, Fernbook deletes it permanently.\n"
        ),
    ),
]

RELEASE = [
    dict(
        id="rn-r01",
        violations=["contractions", "preamble", "rn_version_title", "rn_no_commit_prefixes"],
        text=(
            "# What's new in Fernbook\n\n"
            "We're excited to share this month's updates!\n\n"
            "## New\n\n- feat(search): search now matches words inside attachments.\n\n"
            "## Fixed\n\n- Tags save again when you rename them, which didn't work before.\n"
        ),
    ),
    dict(
        id="rn-r02",
        violations=["rn_sections", "rn_breaking_migration"],
        text=(
            "# Orbitly API 3.0 release notes\n\n"
            "## Highlights\n\n- Webhooks retry failed deliveries up to 5 times.\n\n"
            "## Breaking\n\n- We removed the `page` parameter from `GET /v3/events`.\n"
        ),
    ),
    dict(
        id="rn-r03",
        violations=["rn_no_internal", "rn_user_impact", "monospace", "acronyms"],
        notes="Lists internal work, describes a fix by its code path, and leaves NPE and MIME unexplained.",
        text=(
            "# Fernbook 2.6 release notes\n\n"
            "## Improved\n\n"
            "- Refactored the sync queue into three worker modules.\n"
            "- Bumped the test runner to the latest version.\n"
            "- Notebooks with over 1,000 notes open twice as fast.\n\n"
            "## Fixed\n\n- Resolved an NPE in AttachmentUploader when the MIME type was empty.\n"
        ),
    ),
    dict(
        id="rn-r04",
        violations=["sentence_length", "passive_voice", "oxford_comma", "hedging"],
        text=(
            "# Kestrel Sync 4.2 release notes\n\n"
            "## New\n\n"
            "- Selective sync is now available on every plan, and folders can be excluded by an admin from the web "
            "console without any change to the desktop apps that people use every day.\n"
            "- Sync history now shows uploads, downloads and deletions.\n\n"
            "## Fixed\n\n- Large files probably resume faster after a dropped connection.\n"
        ),
    ),
    dict(
        id="rn-r05",
        violations=[],
        text=(
            "# Fernbook 2.5 release notes\n\n"
            "## New\n\n- Export a notebook as Markdown from **File** > **Export**.\n\n"
            "## Fixed\n\n- Tags now save when you rename a notebook.\n"
        ),
    ),
    dict(
        id="rn-r06",
        violations=[],
        text=(
            "# Orbitly API 3.1 release notes\n\n"
            "## Improved\n\n- `GET /v3/events` responds up to 40 percent faster for large accounts.\n\n"
            "## Breaking\n\n- The `limit` parameter now caps at 200. To keep your current page size, switch to "
            "cursor pagination with the `cursor` parameter.\n"
        ),
    ),
    dict(
        id="rn-r07",
        violations=["link_text", "numerals", "ui_bold"],
        notes="'twelve' must be a numeral, and the Pin menu name is not bold.",
        text=(
            "# Quillpad 1.8 release notes\n\n"
            "## New\n\n"
            "- You can now pin up to twelve notes per notebook. Open the Pin menu to try it.\n"
            "- Read the full details [here](https://example.com/blog).\n"
        ),
    ),
    dict(
        id="rn-r08",
        violations=["em_dash", "back_reference"],
        text=(
            "# Tessellate 5.0 release notes\n\n"
            "## New\n\n"
            "- Batch export -- export up to 50 images in one step.\n"
            "- Smart crop suggests a crop for each image.\n\n"
            "## Improved\n\n- Both tools are faster. The former works with every format; the latter works with PNG "
            "and JPG only.\n"
        ),
    ),
]

MICROCOPY = [
    dict(
        id="ui-r01",
        violations=["preamble", "ui_button_punctuation", "ui_error_no_exclamation", "ui_no_blame", "ui_error_next_step"],
        notes="The error blames the reader and offers no next step.",
        text="# Export dialog\n\ntitle: Export your notebook\nbutton: Export now!\nerror: Oops! You entered an invalid file name.\n",
    ),
    dict(
        id="ui-r02",
        violations=["link_text", "ui_empty_state_action"],
        notes="The first empty state gives no reason and no next action.",
        text=(
            "# Empty states\n\nempty_state: Nothing here.\n"
            "empty_state: You have no tags yet. Create a tag to group related notes.\n"
            "tooltip: Click here to learn about sharing settings\n"
        ),
    ),
    dict(
        id="ui-r03",
        violations=["ui_length", "contractions"],
        text=(
            "# Setup wizard\n\nbutton: Save and continue to the next step of setup\n"
            "error: We couldn't reach the server. Check your connection, then try again.\n"
            "toast: Your changes are saved.\n"
        ),
    ),
    dict(
        id="ui-r04",
        violations=["sentence_length", "ui_button_verb", "all_caps", "ui_error_next_step"],
        notes="'Notebook settings' is a noun phrase on a button, and the error shouts and offers no next step.",
        text=(
            "# Upload\n\nbutton: Notebook settings\nbutton: Cancel\n"
            "error: ERROR: The upload failed because the file is larger than the 25 MB limit for your current plan "
            "and the server rejected the request for that reason.\n"
        ),
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
            "error: The export failed. Check your connection, then try again.\n"
            "empty_state: No exports yet. Export a notebook to see it here.\n"
            "tooltip: Exports include attachments up to 25 MB each.\n"
        ),
    ),
    dict(
        id="ui-r07",
        path="locales/en.json",
        violations=[],
        text=json.dumps({
            "share": {
                "button": "Share notebook",
                "error_no_access": "You do not have access to this notebook. Ask the owner to share it with you.",
                "empty_state": "No one has access yet. Share the notebook to invite your team.",
            }
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
            "heading_case", "contractions", "api_endpoint", "api_params_table", "api_error_response",
            "api_example", "api_auth", "api_response_fields",
        ],
        text="# Delete A Single Note\n\nThis endpoint deletes a note. It's permanent.\n\nThe note ID goes in the path.\n",
    ),
    dict(
        id="api-r02",
        violations=["api_params_table"],
        text=(
            "# List events\n\n"
            "List the events in an account. Authenticate with an API key in the `Authorization` header.\n\n"
            "`GET /v3/events`\n\n"
            "| Parameter | Description |\n|---|---|\n| `limit` | Events per page, up to 200. |\n\n"
            "A successful response returns an `events` array and a `next_cursor` string. "
            "The `next_cursor` field is empty on the last page.\n\n"
            "An invalid key returns `401`.\n\n"
            f"{FENCE}bash\ncurl -H \"Authorization: Bearer $ORBITLY_KEY\" https://api.example.com/v3/events\n{FENCE}\n"
        ),
    ),
    dict(
        id="api-r03",
        violations=["api_auth", "api_response_fields", "one_term_per_concept"],
        notes="No authentication, no response fields, and 'hook' replaces 'webhook'.",
        text=(
            "# Create a webhook\n\n"
            "Create a webhook to receive events at your own URL.\n\n"
            "`POST /v3/webhooks`\n\n"
            "| Name | Type | Required | Description |\n|---|---|---|---|\n"
            "| `url` | string | Yes | The HTTPS endpoint that receives events. |\n"
            "| `events` | array | No | Event types to send. Defaults to all. |\n\n"
            f"{FENCE}json\n{{\"url\": \"https://hooks.example.com/orbitly\"}}\n{FENCE}\n\n"
            "The call returns the new hook. A bad URL returns `422`.\n"
        ),
    ),
    dict(
        id="api-r04",
        violations=["filler", "sentence_length", "back_reference", "latin_abbrev"],
        text=(
            "# Get a note\n\n"
            "Get one note by its ID. Authenticate with an API key in the `Authorization` header.\n\n"
            "`GET /v2/notes/{id}`\n\n"
            "| Name | Type | Required | Description |\n|---|---|---|---|\n| `id` | string | Yes | The note ID. |\n\n"
            "Please note that the response contains the note's `title`, `body`, and `updated_at` fields, and if the "
            "note sits in an archived workspace the response also contains an `archived` flag set to true.\n\n"
            f"{FENCE}bash\ncurl -H \"Authorization: Bearer $FERNBOOK_KEY\" https://api.example.com/v2/notes/n_123\n{FENCE}\n\n"
            "If the note does not exist, the API returns `404`. "
            "The code mentioned above also covers deleted notes, i.e. notes in the trash.\n"
        ),
    ),
    dict(
        id="api-r05",
        violations=[],
        text=(
            "# Delete a webhook\n\n"
            "Delete a webhook to stop event deliveries to its URL. "
            "Authenticate with an API key in the `Authorization` header.\n\n"
            "`DELETE /v3/webhooks/{id}`\n\n"
            "| Name | Type | Required | Description |\n|---|---|---|---|\n| `id` | string | Yes | The webhook ID. |\n\n"
            "A successful call returns `204` with an empty body. An unknown ID returns `404`.\n\n"
            f"{FENCE}bash\ncurl -X DELETE -H \"Authorization: Bearer $ORBITLY_KEY\" "
            f"https://api.example.com/v3/webhooks/wh_123\n{FENCE}\n"
        ),
    ),
    dict(
        id="api-r06",
        violations=[],
        text=(
            "# List notes\n\n"
            "List the notes in a workspace, newest first. Authenticate with an API key that has the `notes:read` scope.\n\n"
            "`GET /v2/notes`\n\n"
            "| Name | Type | Required | Description |\n|---|---|---|---|\n"
            "| `workspace_id` | string | Yes | The workspace to list. |\n"
            "| `limit` | integer | No | Notes per page, from 1 to 100. Defaults to 20. |\n\n"
            "A successful response returns a `notes` array and a `next_cursor` string. "
            "Each note has an `id`, a `title`, and an `updated_at` timestamp.\n\n"
            "An invalid key returns `401`. An unknown workspace returns `404`.\n\n"
            f"{FENCE}bash\ncurl -H \"Authorization: Bearer $FERNBOOK_KEY\" "
            f"\"https://api.example.com/v2/notes?workspace_id=ws_1\"\n{FENCE}\n"
        ),
    ),
    dict(
        id="api-r07",
        violations=["second_person", "hedging"],
        text=(
            "# Rotate an API key\n\n"
            "Rotate a key to replace it without downtime. Authenticate with an admin API key.\n\n"
            "`POST /v2/keys/{id}/rotate`\n\n"
            "| Name | Type | Required | Description |\n|---|---|---|---|\n"
            "| `id` | string | Yes | The key to rotate. |\n"
            "| `grace_period` | integer | No | Seconds the old key keeps working. Defaults to 3600. |\n\n"
            "The response returns the new key in a `key` field. "
            "The developer should probably store the new key before the grace period ends.\n\n"
            "A key that is already rotating returns `409`.\n\n"
            f"{FENCE}bash\ncurl -X POST -H \"Authorization: Bearer $FERNBOOK_ADMIN_KEY\" "
            f"https://api.example.com/v2/keys/k_1/rotate\n{FENCE}\n"
        ),
    ),
    dict(
        id="api-r08",
        violations=["monospace", "numerals"],
        notes="'Authorization header' needs backticks, and 'fifteen' must be a numeral.",
        text=(
            "# Upload an attachment\n\n"
            "Upload a file and attach it to a note. Authenticate with an API key in the Authorization header.\n\n"
            "`POST /v2/notes/{id}/attachments`\n\n"
            "| Name | Type | Required | Description |\n|---|---|---|---|\n"
            "| `id` | string | Yes | The note ID. |\n| `file` | file | Yes | The file to upload, up to 25 MB. |\n\n"
            "The response returns the attachment `id`, `size`, and `content_type`. Files over the limit return `413`. "
            "You can attach up to fifteen files to one note.\n\n"
            f"{FENCE}bash\ncurl -F \"file=@diagram.png\" -H \"Authorization: Bearer $FERNBOOK_KEY\" "
            f"https://api.example.com/v2/notes/n_1/attachments\n{FENCE}\n"
        ),
    ),
]

SETS = {"kb_article": KB, "release_note": RELEASE, "ui_microcopy": MICROCOPY, "api_doc": API}


def main() -> None:
    out_dir = Path(__file__).resolve().parents[1] / "data" / "reviewer"
    out_dir.mkdir(parents=True, exist_ok=True)
    for content_type, items in SETS.items():
        with open(out_dir / f"{content_type}.jsonl", "w", encoding="utf-8") as fh:
            for item in items:
                record = {"id": item["id"], "content_type": content_type, **{k: v for k, v in item.items() if k != "id"}}
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"wrote {len(items)} items to {content_type}.jsonl")


if __name__ == "__main__":
    main()

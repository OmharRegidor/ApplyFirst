# Agad Apply Fill

Fills the onlinejobs.ph Apply pop-up with the Subject and Message from your V1 Agad email. It never presses Send.

## Load it in Chrome (once)

1. Open `chrome://extensions`.
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked** and pick this `extension/` folder.
4. Check that "Agad Apply Fill" shows no errors.
5. In an Agad email, click **Apply on onlinejobs.ph**, then press Apply on the job page.

After you change any file here, click the reload arrow on the extension card.

## What you will see

- First time the pop-up opens: empty Subject and Message boxes are filled, and a notice says "Subject and Message filled. Review, then Send." for 3 seconds.
- Opened again: a notice with a **Refill** button. Nothing changes until you press it.
- Boxes not found within 8 seconds of pressing Apply: "Fields not found, copy below" and a small copy panel.
- Job opened from search instead of the email: "No saved text for this job".

The text is kept in Chrome's session storage, which is cleared when Chrome closes, and is dropped after 24 hours.

Gmail's link wrapper and Chrome's history can keep the long Apply link. It only holds the same letter that is already in the email.

## Turning it on for new emails (VM)

Only emails written after the server restart carry the filled link. After merging, copy `applyfirst/notify/compose.py` to `/opt/applyfirst/applyfirst/notify/` and `applyfirst/pipeline.py` to `/opt/applyfirst/applyfirst/`, then run `sudo systemctl restart applyfirst.service`.

## Tests

`node --test extension/test/` from the repo root. It uses Node's built-in test runner, nothing to install.

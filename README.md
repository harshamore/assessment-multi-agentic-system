# Operation Quiet Ledger: live AI security tabletop

A Streamlit app for running the tabletop with a room of participants.

* **Participants** scan the QR code, read the briefing, pick a role and answer 16 situations. No sign-in.
  They never see other people's answers, the gap analysis or the Cisco mapping.
* **Facilitator** opens `<app URL>/?admin`, enters the password and gets:
  pace controls and the QR code, a live gap analysis mapped to the Cisco AI Security Framework,
  the Cisco products that close each gap, and every response with CSV export.
* Several sessions (one per customer or workshop) each get their own join link and results.

## Files
| File | What it holds |
| --- | --- |
| `app.py` | Participant and facilitator screens |
| `content.py` | Scenario, situations, taxonomy tags, Cisco mapping: edit content here |
| `scoring.py` | Readiness scoring: 70% detection + 30% decision ownership; under 40 = gap |
| `store.py` | Database access (Postgres in production, SQLite locally) |

## Deploy on Streamlit Community Cloud
1. **Database.** Create a free Postgres database on [Neon](https://neon.tech) or [Supabase](https://supabase.com) and copy its connection string.
   On Supabase use the *Session pooler* URI. Tables are created automatically on first run.
2. **Repository.** Push this folder to a GitHub repository (private is fine). Do not commit `.streamlit/secrets.toml`.
3. **App.** At [share.streamlit.io](https://share.streamlit.io): *Create app* → pick the repo, branch and `app.py`.
   Under *Advanced settings → Secrets*, paste the three values from `.streamlit/secrets.example.toml`.
   After the first deploy, set `APP_URL` to the app's real address.
4. **Sharing.** In the app's *Settings → Sharing*, make the app **public** so participants can join without a Streamlit account.
   Results stay behind `ADMIN_PASSWORD`.
5. **Before each session.** Open the app a few minutes early: Community Cloud puts idle apps to sleep.
   In the facilitator view, create a session for the workshop and put its QR code on screen.

## Run locally
```
pip install -r requirements.txt
echo 'ADMIN_PASSWORD = "test"' > .streamlit/secrets.toml
streamlit run app.py          # participants: http://localhost:8501   facilitator: http://localhost:8501/?admin
```
Without `DATABASE_URL` it uses a local `ttx.db` SQLite file.

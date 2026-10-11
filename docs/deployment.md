# Deployment and developer workflow

## Streamlit Community Cloud

Deploy through Streamlit Community Cloud's native GitHub integration. No
second hosting provider, deployment token, API key, or database is required
for the current public FastF1 and synthetic-demo workflows.

1. Push this repository to GitHub and sign in to
   [Streamlit Community Cloud](https://share.streamlit.io/) with the GitHub
   account that can access the repository. Connect GitHub when prompted.
2. In the workspace choose **Create app**, then select the repository, branch
   `main`, and entrypoint file `app.py`.
3. In **Advanced settings**, select Python 3.11, which is the project's
   configured minimum and the version used by CI. No secrets are currently
   required; leave the Secrets field empty.
4. Deploy. Open the app URL and verify the overview and sidebar pages render.
   To verify public-data retrieval, use **F1 Telemetry Explorer** and request
   an event/session. A missing network connection, unavailable upstream data,
   or an unsupported session is reported in the UI; no synthetic data is
   substituted. Inspect the app's **Manage app** logs in the Cloud workspace
   if build or runtime errors occur.
5. FastF1 cache files are stored under the operating system's temporary
   directory by default. Hosted cache storage is disposable and may be cleared
   when the app restarts. `F1_CACHE_DIR` is an optional local/runtime
   environment override, not a credential, and is not needed in Cloud.
   Dashboard report downloads are assembled in memory; the app does not need
   persistent local report storage. The standalone reporting pipeline writes
   to `reports/` only when a developer runs it explicitly.
6. When a tested change is merged into `main`, Streamlit Community Cloud's
   GitHub integration detects the commit and updates the app. Confirm the
   deployed commit/build in the Cloud workspace and reload the app URL.

The app currently reads no values from `st.secrets`. If credentials become
necessary in a future feature, keep them out of Git and enter only the needed
TOML values under the app's **Advanced settings / Secrets** in Community
Cloud. For local development, a private `.streamlit/secrets.toml` is ignored by
Git; `.env.example` contains only safe non-secret guidance.

## Local and GitHub workflow

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check .
python -m compileall -q app.py src pages tests
python -m pip check
python -m streamlit run app.py
```

For each change, create a feature branch, make the change, run the checks
above, and push that feature branch. Review the GitHub Actions result for the
push and pull request, then merge into `main` after the checks pass. Finally,
confirm that Streamlit Community Cloud has deployed the resulting `main`
commit. The workflow defines CI checks; repository branch protection or
mandatory status-check settings must be configured separately in GitHub and
are not asserted by this project.

The workflow runs on pushes to every branch and on pull requests targeting
`main`. It requests only read access to repository contents, uses no secrets,
and contains no deployment job. Tests use local fixtures/mocks and do not
make live FastF1 requests.

## References

- [Deploy an app on Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
- [Community Cloud app dependencies and Python version](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)
- [Manage Community Cloud secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)
- [Manage a deployed app](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app)

# openalex-kz — CI/CD with Docker and Jenkins

`collectors/openalex_kz.py` is a data-collection script from my PhD research. It
downloads from the [OpenAlex API](https://docs.openalex.org) every 2020–2026
publication with at least one author from a Kazakhstani university, plus the
profiles of those authors. The script is resumable: each step saves its progress
and continues where it stopped.

This repository puts that script into a Jenkins CI pipeline: on every commit
Jenkins runs the unit tests, builds a Docker image and smoke-tests it.

## Layout

```
collectors/openalex_kz.py   the script (steps: institutions, works, authors)
collectors/common.py        helpers imported by openalex_kz.py (copied unchanged)
tests/test_openalex_kz.py   pytest unit tests for openalex_kz.py, OpenAlex API is mocked
Dockerfile                  multi-stage: base -> test (pytest) / runtime (shipped image)
Jenkinsfile                 declarative CI pipeline
jenkins/                    local Jenkins server (Docker Compose + Docker CLI + plugins)
```

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -v                                  # 11 tests
python -m collectors.openalex_kz institutions        # real API call
```

## Run with Docker

```bash
docker build --target test -t openalex-kz:test . && docker run --rm openalex-kz:test   # tests
docker build --target runtime -t openalex-kz .
docker run --rm -v "$PWD/data:/app/data" openalex-kz institutions
docker run --rm -v "$PWD/data:/app/data" --env-file .env openalex-kz works authors
```

The `--env-file .env` part is optional (see `.env.example`). Without
`OPENALEX_API_KEY`, OpenAlex allows about 1000 requests per day.

## Jenkins

1. Start the server:
   ```bash
   cd jenkins && docker compose up -d --build
   docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
   ```
   Open http://localhost:8080, paste the password, then choose *Install suggested
   plugins* (the ones the pipeline needs are already installed from
   `jenkins/plugins.txt`) and create an admin user.
2. Go to *New Item → Pipeline* and name it `openalex-kz`. Under *Pipeline* pick
   **Pipeline script from SCM**, set SCM to *Git*, enter this repository's URL and
   branch `*/main`. Script Path: `Jenkinsfile`.
3. Click **Build Now** once. Jenkins then registers the `triggers {}` block from
   the Jenkinsfile.
4. To trigger on every commit, Jenkins needs to hear about pushes in one of two ways:
   * **Polling (works out of the box):** `pollSCM('H/2 * * * *')` checks the repo
     every 2 minutes and builds when there are new commits.
   * **Webhook (instant):** expose Jenkins with something like
     `ngrok http 8080`. Then on GitHub go to *Settings → Webhooks* and add
     `https://<ngrok-host>/github-webhook/` with content type
     `application/json` and the *push* event. The `githubPush()` trigger
     handles it.

Pipeline stages: **Checkout → Unit tests** (JUnit report published) **→ Build
Docker image** (tags `BUILD_NUMBER`, short commit SHA, `latest`) **→ Smoke test
image**.

# Practical Task: CI Pipeline for a Python Research Project with Docker and Jenkins

**Student:** ______________________   **Repository:** https://github.com/______/openalex-kz-cicd

## 1. Project

The project is `openalex_kz.py`, a data-collection script from my dissertation on
scientific collaboration in Kazakhstan. It downloads from the OpenAlex API:

* the list of Kazakhstani universities;
* every 2020–2026 publication with at least one author from them;
* the profiles of those authors.

Results are saved as JSONL files. The script has two download modes. With an API
key it uses cursor pagination. Without a key it pages through results; when a
slice has more than 10,000 records, it splits the list of universities in half.
It saves its state after every page, so a crashed run continues where it stopped.
The pipeline covers only this script. `common.py` is copied unchanged because
`openalex_kz.py` imports its HTTP and file helpers.

## 2. Steps

1. **Repository.** I moved `openalex_kz.py` (with the `common.py` it imports) into a standalone
   repository on GitHub, added `requirements.txt` and `requirements-dev.txt`, and
   set up `.gitignore`/`.dockerignore` so that collected data and the `.env` file
   with the API key never reach Git or an image.
2. **Unit tests for `openalex_kz.py` (pytest, 11 tests).** The real API is slow, rate-limited and
   needs a key, so all tests replace the HTTP layer with fakes and run in a
   temporary directory. They cover:
   * ID parsing and request parameters;
   * error handling in `fetch`;
   * excluding schools and research institutes from the university list;
   * splitting slices larger than 10,000 records, and resuming after a restart;
   * saving the cursor state;
   * selecting only authors from Kazakhstani universities who have not been
     downloaded yet;
   * choosing the download mode and running the requested steps from the CLI.
3. **Dockerfile (multi-stage).**
   * The `base` stage installs only the runtime dependencies.
   * The `test` stage adds pytest and the tests. Its command runs pytest and
     writes a JUnit XML report.
   * The `runtime` stage is the shipped image. It runs as a non-root user and
     keeps collected data in a `/app/data` volume. Its entrypoint is
     `python -m collectors.openalex_kz`, so a step name can be passed as an
     argument (`docker run ... openalex-kz works`).
4. **Jenkins server.** Jenkins LTS runs locally in Docker Compose (`jenkins/`).
   A custom image adds the Docker CLI and preinstalls the plugins (Pipeline, Git,
   GitHub, JUnit, Timestamper, Stage View). The host Docker socket is mounted, so
   Jenkins builds images with the host daemon. That way I did not need
   Docker-in-Docker.
5. **Pipeline (`Jenkinsfile`, declarative).** The stages are:
   * **Checkout**;
   * **Unit tests:** build the `test` target, run it, copy `junit.xml` out of
     the container and publish it with `junit`. A failing test fails the build;
   * **Build Docker image:** the `runtime` target, tagged with the build number,
     the short commit SHA and `latest`;
   * **Smoke test:** import the module inside the new image.

   Two triggers start a build on every commit: `githubPush()` for a GitHub
   webhook, and `pollSCM('H/2 * * * *')` as a fallback.

Screenshots (in `screenshots/`):

* the job's Stage View with all stages green;
* the console log;
* the test result trend / JUnit report;
* a red build caused by a deliberately broken test;
* `docker image ls openalex-kz` showing the built tags.

## 3. Difficulties

* **Tests and an external API.** Unit tests had to run with no network access and
  no API key, and had to be repeatable. I solved this by replacing `fetch` and
  `get_json` with fakes, and by disabling `time.sleep` in
  tests. The whole suite now runs in under a second.
* **Relative paths.** The script writes to `data/raw/openalex` relative to the
  working directory. Each test changes into its own temporary directory, so tests
  never touch real data and do not affect each other.
* **Docker inside Jenkins.** The official Jenkins image has no Docker CLI, and on
  Docker Desktop the mounted `/var/run/docker.sock` belongs to root. I built a
  custom Jenkins image with `docker-ce-cli` and ran the container as root. That
  is acceptable for a local training setup but not for production, where a
  separate build agent or rootless Docker would be the right choice.
* **Test report when tests fail.** If pytest runs inside `docker build`, a failure
  stops the build and the report is lost. Instead, I build the test image first,
  run tests with `docker run`, and copy `junit.xml` out in a `post { always }`
  block. Jenkins shows which tests failed even on a red build.
* **"On every commit" with a local Jenkins.** GitHub cannot reach `localhost`, so
  a webhook needs a tunnel such as ngrok. I kept SCM polling every 2 minutes as a
  fallback. The drawback of polling is that several commits pushed within the
  same 2-minute window are built together.
* **Secrets.** The OpenAlex API key stays in `.env`, which is excluded from Git
  and from the build context. The container gets it only at run time via
  `--env-file`.

## 4. Conclusions

The research script now has an automated check on every change. A regression in
the pagination, resume or filtering logic is caught by the tests before it can
spoil a multi-hour data download. The multi-stage Dockerfile keeps the shipped
image small and free of test tools, while the same file defines the test
environment, so CI and local runs behave the same. Running Jenkins itself in
Docker made the CI server reproducible with one `docker compose up` command.
Possible next steps:

* push the image to Docker Hub;
* deploy to a test server or Minikube;
* add a linter stage (ruff) and a coverage report.

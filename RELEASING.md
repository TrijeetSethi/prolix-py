# Releasing

Releases are published to PyPI by GitHub Actions. Nobody uploads by hand and
no PyPI token is stored anywhere. PyPI trusts the `release.yml` workflow of
this repository through trusted publishing.

## Branches

| Branch | Purpose | Publishes |
|--------|---------|-----------|
| `main` | Development. Every change lands here through a pull request. | Never |
| `beta` | Pre-releases for testing, such as `0.4.0b1` or `0.4.0rc1`. | A pre-release version that is not on PyPI yet |
| `release` | Final releases, such as `0.4.0`. | A final version that is not on PyPI yet |

`beta` and `release` only ever move forward to a commit of `main`, or to a
hotfix that is merged back into `main` right after. A push to either branch
runs the release workflow, which decides what to do from the version in
`src/clarity_score/__init__.py`.

- The version is already on PyPI: nothing is published. Only CI runs.
- The version is new and matches the branch: CI runs, then the tested sdist and
  wheel are published to PyPI, the commit is tagged `v<version>` and a GitHub
  release is created with the changelog section as its notes. A release from
  `beta` is marked as a pre-release.
- The version is new but does not match the branch, such as a final version on
  `beta`: the workflow fails and nothing is published.

A final release also needs a dated changelog heading, such as
`## [0.4.0] - 2026-12-01`. The workflow refuses a heading marked Unreleased. A
pre-release such as `0.4.0b1` may use the `## [0.4.0] - Unreleased` section.

## Publish a pre-release

1. On `main`, set `__version__` in `src/clarity_score/__init__.py` to the
   pre-release, for example `0.4.0b1`, and make sure `CHANGELOG.md` has a
   `## [0.4.0]` section. Merge that change into `main`.
2. Move `beta` to that commit:

   ```bash
   git switch main && git pull
   git push origin main:beta
   ```

3. Watch the Release workflow in the Actions tab. Install the result with
   `pip install --pre clarity-score==0.4.0b1`.

For another pre-release, bump to `0.4.0b2` or `0.4.0rc1` and repeat.

## Publish a final release

1. On `main`, set `__version__` to the final version, for example `0.4.0`, and
   date its heading in `CHANGELOG.md`, for example `## [0.4.0] - 2026-12-01`.
   Merge that change into `main`.
2. Move `release` to that commit:

   ```bash
   git switch main && git pull
   git push origin main:release
   ```

3. Optionally also run `git push origin main:beta` so that `beta` is not behind.
   The version is already published by then, so that push publishes nothing.

## Hotfix

Branch from `release`, fix the bug, bump the patch version (for example
`0.4.1`), date its changelog section and open a pull request into `release`.
After it is merged and published, merge `release` back into `main`.

## Check a release before pushing

The workflow decides with `.github/scripts/release_plan.py`, which you can run
locally. It reads the version and the changelog, asks PyPI whether the version
exists and prints the decision.

```bash
python .github/scripts/release_plan.py --registry pypi --branch release
python .github/scripts/release_plan.py --registry pypi --branch beta
```

## If a publish fails

Rerun the failed job from the Actions tab. If the upload reached PyPI but a
later step failed, rerunning is still safe, because the tag and release step
skips a release that already exists. PyPI never accepts the same version twice,
so a version that was published with a mistake is fixed by publishing the next
version, not by uploading again. A broken version can be yanked on PyPI.

## One-time setup

These steps are needed once, before the first release.

1. **Register the pending publisher on PyPI.** Signed in as the account that
   will own the project, open <https://pypi.org/manage/account/publishing/> and
   add a GitHub publisher with these values.

   | Field | Value |
   |-------|-------|
   | PyPI project name | `clarity-score` |
   | Owner | `TrijeetSethi` |
   | Repository name | `vague-py` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

   The first publish creates the project. A pending publisher does not reserve
   the name, so publish soon after adding it.

2. **Check the GitHub environment.** The repository has an environment named
   `pypi` that only the `beta` and `release` branches can deploy to. Add
   yourself as a required reviewer there if every publish should wait for an
   approval.

3. **Turn publishing on.** Publishing stays off until the repository variable
   `PUBLISH_ENABLED` is `true`. Until then a push to `beta` or `release` runs
   the checks and reports what it would publish.

   ```bash
   gh variable set PUBLISH_ENABLED --body true --repo TrijeetSethi/vague-py
   ```

4. **Make the repository public** before the first final release, so that the
   project links on PyPI work and Sigstore attestations are published with the
   distributions. The workflow makes attestations only for a public repository.

# Contributing

Contributions are welcome, and they are greatly appreciated! Every little helps, and credit will always be given.

You can contribute in many ways:

## Types of Contributions

### Report Bugs

Report bugs to [our issue page][gh-issues]. If you are reporting a bug, please include:

- Your operating system name and version.
- Any details about your local setup that might be helpful in troubleshooting.
- Detailed steps to reproduce the bug.

### Fix Bugs

Look through the GitHub issues for bugs. Anything tagged with "bug" and "help wanted" is open to whoever wants to implement it.

### Implement Features

Look through the GitHub issues for features. Anything tagged with "enhancement" and "help wanted" is open to whoever wants to implement it.

### Write Documentation

ICOMON Kitchen Scale could always use more documentation, whether as part of the official ICOMON Kitchen Scale docs, in docstrings, or even on the web in blog posts, articles, and such.

### Submit Feedback

The best way to send feedback [our issue page][gh-issues] on GitHub. If you are proposing a feature:

- Explain in detail how it would work.
- Keep the scope as narrow as possible, to make it easier to implement.
- Remember that this is a volunteer-driven project, and that contributions are welcome 😊

## Get Started!

Ready to contribute? Here's how to set yourself up for local development.

1. Fork the repo on GitHub.

2. Clone your fork locally:

   ```shell
   $ git clone git@github.com:your_name_here/icomon-kitchen-scale.git
   ```

3. Install the project dependencies with [uv](https://docs.astral.sh/uv/):

   ```shell
   $ uv sync
   ```

4. Create a branch for local development:

   ```shell
   $ git checkout -b name-of-your-bugfix-or-feature
   ```

   Now you can make your changes locally.

5. When you're done making changes, check that your changes pass our tests:

   ```shell
   $ uv run pytest
   ```

6. Linting and tests run through [prek](https://prek.j178.dev/) before each commit:

   ```shell
   $ prek install -f
   ```

   This runs ruff, mypy, and pytest for changed files only. To run all hooks manually:

   ```shell
   $ prek run -a
   ```

7. Commit your changes and push your branch to GitHub:

   ```shell
   $ git add .
   $ git commit -m "feat(something): your detailed description of your changes"
   $ git push origin name-of-your-bugfix-or-feature
   ```

   Note: the commit message should follow [the conventional commits](https://www.conventionalcommits.org).

8. Submit a pull request through the GitHub website or using the GitHub CLI (if you have it installed):

   ```shell
   $ gh pr create --fill
   ```

## Pull Request Guidelines

We like to have the pull request open as soon as possible, that's a great place to discuss any piece of work, even unfinished. You can use draft pull request if it's still a work in progress. Here are a few guidelines to follow:

1. Include tests for feature or bug fixes.
2. Update the documentation for significant features.
3. Ensure tests are passing on CI.

## Tips

To run a subset of tests:

```shell
$ pytest tests
```

## Making a new release

Releases are managed with [Release Drafter](https://github.com/release-drafter/release-drafter). When changes are merged to `main`, a draft release is updated automatically based on PR labels. To publish:

1. Review the draft release on GitHub.
2. Publish the release — this triggers the `release` workflow to publish to PyPI.

Ensure [trusted publishing](https://docs.pypi.org/trusted-publishers/) is configured for the project on PyPI.

[gh-issues]: https://github.com/icomon/icomon-kitchen-scale/issues

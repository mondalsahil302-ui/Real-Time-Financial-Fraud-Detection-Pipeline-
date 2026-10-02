# Contributing

## Development Setup

- Use Python 3.11 or newer, Java 17 or newer, and Docker Desktop with Compose.
- Create and activate a virtual environment, then install `requirements.txt`.
- Install `xgboost` for the second-stage model and cascade streaming scripts.
- Copy environment-specific settings into a local `.env`; never commit credentials.

## Local Validation

- Validate service configuration with `docker compose config -q`.
- Start dependencies with `docker compose up -d` before running the Kafka and Cassandra smoke checks.
- Compile changed Python files before opening a pull request.
- For changes to model features, verify the feature manifest, model artifact, and configuration remain aligned.

## Pull Requests

- Use a short branch name such as `fix/kafka-delivery-timeout` or `docs/contributing-guide`.
- Keep changes focused and include the reason for behavioral changes.
- Record commands run and their outcomes in the pull request description.
- Do not include local credentials, virtual environments, checkpoints, or generated datasets unless specifically required.

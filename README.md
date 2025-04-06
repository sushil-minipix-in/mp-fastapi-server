# OTT API

## Initial Setup

Run `make setup` to configure git hooks after initial cloning of repo

## Install dependencies

- Use Poetry to manage direct dependencies
- DO NOT change requirements.txt manually, any dependencies handled by poetry will ensure updated requirements.txt using pre-commit hook

## How to start

For development container, use `uvicorn app:app --host 0.0.0.0 --reload`
In prod, run the container from the docker image created from the Dockerfile

## Environment Variables

Check app/config.py for required env variables

## DB Indexes

- email, apple_id, mobile in users collection
- date in orders collection
- email in admins collection
- unique('name') in artists collection

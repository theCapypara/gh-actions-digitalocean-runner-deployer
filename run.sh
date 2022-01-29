#!/bin/sh
# Simple Docker-based run script that builds the images locally and uses a ./env file.
docker run --rm --env-file ($pwd)/.env .

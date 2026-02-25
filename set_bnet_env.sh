#!/usr/bin/env bash

read -r -p "BLIZZARD_CLIENT_ID: " BLIZZARD_CLIENT_ID
read -r -s -p "BLIZZARD_CLIENT_SECRET: " BLIZZARD_CLIENT_SECRET
echo

if [[ -z "$BLIZZARD_CLIENT_ID" || -z "$BLIZZARD_CLIENT_SECRET" ]]; then
  echo "Both values are required."
  return 1 2>/dev/null || exit 1
fi

export BLIZZARD_CLIENT_ID
export BLIZZARD_CLIENT_SECRET

echo "Credentials exported for this terminal session."

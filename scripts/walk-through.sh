#!/usr/bin/env bash
# Prepares a throwaway broker office and starts the application against it,
# so that a person can walk the path from folder to hand-over
# (docs/development.md, section “Walk-through”).
#
# Everything goes into one folder in the home directory, because the shell
# only lets the sidecar read below the home directory, /media, /mnt and /srv:
#
#   scans/      the watched folder, one subfolder per customer
#   scans/Ausgabe/  where the hand-over goes, created when scans/ is chosen
#   share/      XDG_DATA_HOME of the application, so that its data directory
#               holds a profile with a synthetic `hand_over` block and leaves
#               the real data directory and the shipped profile untouched
#
# The folder is wiped and rebuilt at every start. Usage:
#   npm run walk-through            # folder ~/substrakt-walk-through
#   WALK_THROUGH_DIR=<dir> npm run walk-through
#   WALK_THROUGH_PROFILE=<file.yml>  # another profile than the shipped example
#   WALK_THROUGH_PREPARE_ONLY=1      # prepare the folder, start nothing
#
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shortcut: XDG_DATA_HOME moves the data directory on Linux only; macOS and
# Windows need another way before the walk-through runs there.
if [[ "$(uname -s)" != Linux ]]; then
  echo "The walk-through runs on Linux and WSL2 only." >&2
  exit 1
fi

WALK="${WALK_THROUGH_DIR:-$HOME/substrakt-walk-through}"
PROFILE="${WALK_THROUGH_PROFILE:-$ROOT/sidecar/substrakt/pipeline_profiles/insurance_folder.yml}"
if [[ ! -f "$PROFILE" ]]; then
  echo "No profile file at $PROFILE." >&2
  exit 1
fi
MARKER="$WALK/.substrakt-walk-through"
# A later arrival is copied this many seconds after the start, while the
# first import is still on Overview.
LATER_ARRIVAL_SECONDS=90

if [[ -e "$WALK" && ! -e "$MARKER" ]]; then
  echo "$WALK exists and was not made by this script; it stays as it is." >&2
  echo "Choose another folder with WALK_THROUGH_DIR." >&2
  exit 1
fi
rm -rf "$WALK"

CORPUS="$ROOT/corpus/out/insurance"
[[ -f "$CORPUS/truth.json" ]] || npm run corpus

DATA="$WALK/share/$(node -p "require('./src-tauri/tauri.conf.json').identifier")"
mkdir -p "$DATA/pipeline_profiles" "$DATA/gdv"
touch "$MARKER"

# Three customers. Okafor has a text PDF, a scan and a policy of an insurer
# the walk-through table leaves out, which the simulation holds back.
# Lindqvist's policy comes twice with different bytes, as the same paper
# scanned again would: a possible duplicate.
place() { mkdir -p "$WALK/scans/$1"; cp "$CORPUS/$2" "$WALK/scans/$1/$2"; }
place "Tischlerei Okafor" policy_a_1.pdf
place "Tischlerei Okafor" premium_invoice_c_1_scan300.png
place "Tischlerei Okafor" policy_c_4.pdf
place "Jonas Brandt" policy_b_1.pdf
place "Mira Lindqvist" policy_c_1.pdf
place "Mira Lindqvist" contract_change_b_1_scan300.png
cp "$CORPUS/policy_c_1.pdf" "$WALK/scans/Mira Lindqvist/policy_c_1_again.pdf"
printf '%% scanned again\n' >>"$WALK/scans/Mira Lindqvist/policy_c_1_again.pdf"

# The data directory gets the profile with a hand_over block whose settings
# are invented, and an insurer table without Wattenmeer. A profile that has
# a block already would get a second key, which YAML refuses.
if grep -q '^hand_over:' "$PROFILE"; then
  echo "$PROFILE has a hand_over block already; the walk-through adds its own." >&2
  exit 1
fi
profile="$DATA/pipeline_profiles/$(basename "$PROFILE")"
cp "$PROFILE" "$profile"
cat >>"$profile" <<'EOF'

# SYNTHETIC, for the walk-through only (scripts/walk-through.sh). Encoding,
# record separator, broker number and sender are invented; the real ones are
# facts only the broker and the vendor have. Nobody has imported a file
# written with these settings into any program.
hand_over:
  format: gdv
  encoding: cp850
  record_separator: crlf
  broker_number: "4711"
  sender: Maklerbüro Beispiel
  addressee: Bestandsprogramm
  currency: EUR
  contract_kinds: [policy]
  collection_kinds: [premium_invoice]
EOF
cat >"$DATA/gdv/insurers.yml" <<'EOF'
# SYNTHETIC, for the walk-through only (scripts/walk-through.sh). The
# invented insurers of the corpus without Wattenmeer Assekuranz SE, so that
# one contract is held back for a missing insurer number.
name: insurers
source: Invented numbers for the walk-through; see sidecar/substrakt/gdv/tables/insurers.yml.
entries:
  Nordlicht Versicherung AG: "9901"
  Hansekontor Sachversicherung AG: "9902"
  Alpenrand Versicherung a. G.: "9903"
EOF

if [[ "${WALK_THROUGH_PREPARE_ONLY:-}" == 1 ]]; then
  echo "Prepared $WALK with $(basename "$PROFILE"); nothing started."
  exit 0
fi

(sleep "$LATER_ARRIVAL_SECONDS" && place "Jonas Brandt" premium_invoice_d_1.pdf) &

cat <<EOF

  Walk-through folder: $WALK
    watched folder:   $WALK/scans
    hand-over goes to: $WALK/scans/Ausgabe (created when scans is chosen)
  A later arrival for Jonas Brandt comes $LATER_ARRIVAL_SECONDS seconds after the start.
  The steps are in docs/development.md, section "Walk-through".

EOF

export XDG_DATA_HOME="$WALK/share"
bash scripts/dev-wsl.sh

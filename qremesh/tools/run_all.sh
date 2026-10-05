#!/bin/sh
# Remesh every test shape and print the key numbers on one line each.
# Extra arguments go to `qremesh remesh` (for instance --quads 1000).
cd "$(dirname "$0")/.."
mkdir -p out
make_shape() { [ -f "out/$1.obj" ] || ./target/release/qremesh shape "$2" -o "out/$1.obj" $3; }
make_shape ico ico "--subdivisions 4 --jitter 0"
make_shape icoj ico ""
make_shape cube cube ""
make_shape torus torus "--jitter 0"
make_shape blob1 blob "--seed 1"
make_shape blob2 blob "--seed 2"
make_shape blob3 blob "--seed 3"
make_shape tube tube "--jitter 0"
make_shape annulus annulus "--jitter 0"
make_shape hemi hemi ""
for f in ico icoj cube torus blob1 blob2 blob3 tube annulus hemi; do
  printf "%-7s " $f
  ./target/release/qremesh remesh out/$f.obj -o out/${f}_q.obj --layout out/$f.json "$@" 2>&1 \
    | grep -E "^field|^graph|^quads|panick|^error" \
    | sed 's/.*singularities/sing/; s/graph: [0-9]* -> [0-9]* triangles, [0-9]* crossings, [0-9]* pruned, //; s/, 0 not fillable.*//; s/quads: {"vertices": [0-9]*, "faces": [0-9]*, "quads": \([0-9]*\).*"valence": \([^}]*}\), "singular_vertices": \([0-9]*\).*"edge_length_over_h": {"mean": \([0-9.]*\), "std": \([0-9.]*\).*"distance_from_input": {"mean": \([0-9.]*\), "max": \([0-9.]*\)}.*/quads \1 valence \2 singular \3 edge \4±\5 dist \6\/\7/' \
    | tr '\n' ' '
  echo
done

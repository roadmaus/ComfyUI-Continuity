//! qremesh — Continuity's quad remesher.
//!
//!     qremesh shape ico|cube|torus|blob|sphere|... -o shape.obj [--jitter 0.3]
//!     qremesh remesh in.obj -o out.obj [--quads 600 --features 35 --layout lay.json]
//!
//! `remesh` is the whole pipeline: a global cross field, its singularities,
//! separatrices traced and chosen into a patch layout, the layout cut into
//! the mesh, patch sides quantized, patches filled with grids, the result
//! smoothed back onto the input. A JSON report goes to stdout, progress to
//! stderr, and `--layout` writes the layout for `tools/render_layout.py`.

mod cplx;
mod cross;
mod fill;
mod math;
mod mesh;
mod partition;
mod patches;
mod premesh;
mod proj;
mod quantize;
mod refine;
mod sdf;
mod shapes;
mod trace;

use math::{Rng, V3};
use std::process::ExitCode;
use std::time::Instant;

struct Args {
    words: Vec<String>,
}

impl Args {
    fn flag(&self, name: &str) -> Option<&str> {
        let at = self.words.iter().position(|w| w == name)?;
        self.words.get(at + 1).map(String::as_str)
    }

    fn num<T: std::str::FromStr>(&self, name: &str, default: T) -> Result<T, String> {
        match self.flag(name) {
            None => Ok(default),
            Some(s) => s.parse().map_err(|_| format!("{name}: cannot read {s:?}")),
        }
    }
}

fn main() -> ExitCode {
    let words: Vec<String> = std::env::args().skip(1).collect();
    let result = match words.first().map(String::as_str) {
        Some("shape") => shape(&Args { words }),
        Some("remesh") => remesh(&Args { words }),
        Some("premesh") => premesh_only(&Args { words }),
        _ => Err("usage: qremesh shape NAME -o OUT | qremesh remesh IN -o OUT [--quads N]".into()),
    };
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(message) => {
            eprintln!("error: {message}");
            ExitCode::FAILURE
        }
    }
}

fn shape(args: &Args) -> Result<(), String> {
    let out = args.flag("-o").ok_or("shape needs -o OUT")?;
    let seed: u64 = args.num("--seed", 1)?;
    let mut m = match args.words.get(1).map(String::as_str) {
        Some("ico") => shapes::icosphere(args.num("--subdivisions", 5)?),
        Some("cube") => shapes::cube(args.num("--n", 40)?),
        Some("blob") => shapes::blob(args.num("--subdivisions", 5)?, seed),
        Some("torus") => shapes::torus(1.0, 0.4, args.num("--nu", 160)?, args.num("--nv", 64)?),
        Some("sphere") => mesh::uv_sphere(args.num("--rings", 80)?, args.num("--segments", 160)?, 0.0, seed),
        Some("tube") => shapes::tube(args.num("--nu", 160)?, args.num("--nv", 50)?),
        Some("annulus") => shapes::annulus(args.num("--nu", 200)?, args.num("--nv", 30)?),
        Some("hemi") => shapes::hemisphere(args.num("--subdivisions", 5)?),
        Some("creature") => sdf::mesh(sdf::creature, math::v3(-1.5, -0.6, -0.5), math::v3(1.7, 0.6, 1.7), args.num("--res", 96)?),
        Some("pretzel") => sdf::mesh(sdf::pretzel, math::v3(-1.9, -1.2, -0.5), math::v3(1.9, 1.2, 0.5), args.num("--res", 120)?),
        _ => return Err("shape: ico, cube, torus, blob, sphere, tube, annulus, hemi, creature or pretzel".into()),
    };
    let jitter: f64 = args.num("--jitter", 0.3)?;
    if jitter > 0.0 {
        shapes::jitter(&mut m, jitter, seed);
    }
    let faces: Vec<Vec<u32>> = m.f.iter().map(|t| t.to_vec()).collect();
    mesh::write_obj(out, &m.v, &faces)?;
    eprintln!("{} vertices, {} triangles -> {out}", m.v.len(), m.f.len());
    Ok(())
}

fn remesh(args: &Args) -> Result<(), String> {
    let input = args.words.get(1).ok_or("remesh needs an input OBJ")?;
    let out = args.flag("-o").ok_or("remesh needs -o OUT")?;
    let align: f64 = args.num("--align", 0.005)?;
    let degrees: f64 = args.num("--features", 35.0)?;
    let quads: f64 = args.num("--quads", 600.0)?;
    let mut rng = Rng::new(args.num("--seed", 1)?);

    let clock = Instant::now();
    let m = mesh::read_obj(input)?;
    // Unless asked not to, remesh the input to even triangles a few times
    // smaller than a quad first: everything downstream assumes it.
    let m = if args.words.iter().any(|w| w == "--no-premesh") {
        m
    } else {
        let t = Instant::now();
        let quad = (mesh::surface_area(&m) / quads).sqrt();
        let (pm, r) = premesh::remesh(&m, quad * args.num("--premesh-edge", 0.4)?, degrees, args.num("--premesh-rounds", 6)?);
        eprintln!(
            "premesh: {} -> {} triangles, slivers {:.1}% -> {:.1}%, {} feature edges, {:.2}s",
            m.f.len(), r.triangles, r.slivers_before * 100.0, r.slivers_after * 100.0, r.feature_edges, t.elapsed().as_secs_f64()
        );
        let _ = r.vertices;
        pm
    };
    let s = cross::Surface::new(&m);
    let diameter = {
        let lo = m.v.iter().fold(m.v[0], |a, p| math::v3(a.x.min(p.x), a.y.min(p.y), a.z.min(p.z)));
        let hi = m.v.iter().fold(m.v[0], |a, p| math::v3(a.x.max(p.x), a.y.max(p.y), a.z.max(p.z)));
        (hi - lo).norm()
    };
    let target = cross::guide(&s, args.num("--axes", 0.1)?, diameter);
    let (fixed, sharp) = cross::feature_constraints(&s, degrees);
    let t = Instant::now();
    let field = cross::solve(&s, &target, &fixed, align, &mut rng);
    let t_field = t.elapsed().as_secs_f64();
    let sings = cross::singularities(&s, &field.z);
    let plus = sings.iter().filter(|x| x.index > 0).count();
    let minus = sings.len() - plus;
    eprintln!("field ({}): {} solver iterations, {:.2}s; singularities +{plus} -{minus}", field.how, field.solver_iterations, t_field);

    let edge = mesh::mean_edge(&m);
    let t = Instant::now();
    // The side of a quad, were the surface covered in `--quads` of them.
    let quad = (mesh::surface_area(&m) / quads).sqrt();
    // The layout: cuts on the mesh itself, read back as an exact graph.
    // `--legacy-layout` is the separatrix tracer, kept to compare against
    // until the partition does at least as well on every test shape.
    let legacy = args.words.iter().any(|w| w == "--legacy-layout");
    let (fill_mesh, mut graph, traces, n_traces, t_trace, t_graph, crossings);
    if legacy {
        let lay = trace::layout(&s, &field.z, &sings, &sharp, edge * 0.5, diameter * 3.0, quad);
        t_trace = t.elapsed().as_secs_f64();
        let mut ended: std::collections::BTreeMap<&str, usize> = Default::default();
        for tr in &lay.traces {
            *ended.entry(tr.ended).or_default() += 1;
        }
        eprintln!("layout: {} traces ({ended:?}), {} regions, {} disks, {:.2}s", lay.traces.len(), lay.regions, lay.disks, t_trace);
        let t = Instant::now();
        let polylines: Vec<(&[V3], &[trace::Stop])> = lay.traces.iter().map(|t| (t.points.as_slice(), t.stops.as_slice())).collect();
        let refined = refine::insert(&m, &sharp, &polylines, edge * 0.05);
        graph = patches::build(&refined.m, &refined.cut, &refined.feature, quad, None);
        t_graph = t.elapsed().as_secs_f64();
        crossings = refined.crossings;
        let drawn = if std::env::var("QREMESH_CANDIDATES").is_ok() { &lay.candidates } else { &lay.traces };
        traces = drawn.iter().map(|t| (t.points.clone(), if t.to.is_some() { "edge" } else { t.kind })).collect::<Vec<_>>();
        n_traces = lay.traces.len();
        fill_mesh = refined.m;
    } else {
        let part = partition::layout(&s, &field.z, &sings, &sharp, quad, diameter * 3.0);
        t_trace = t.elapsed().as_secs_f64();
        eprintln!("layout: {} paths ({} added, {} removed), {} patches left invalid, {:.2}s", part.paths.len(), part.added, part.removed, part.invalid, t_trace);
        let t = Instant::now();
        let turn = |u: u32, v: u32, w: u32| part.turn(u, v, w);
        graph = patches::build(&m, &part.cut, &part.feature, quad, Some(&turn));
        let (added, dropped) = graph.fix_corners(&m, 3, 5);
        if added + dropped > 0 {
            eprintln!("corners: {added} added, {dropped} dropped to bring every patch to 3–5");
        }
        t_graph = t.elapsed().as_secs_f64();
        crossings = 0;
        traces = part.paths.iter().map(|p| (p.chain.iter().map(|&v| m.v[v as usize]).collect::<Vec<V3>>(), p.kind)).collect();
        n_traces = part.paths.len();
        fill_mesh = m.clone();
    }
    let mut corner_hist: std::collections::BTreeMap<usize, usize> = Default::default();
    let mut bad = 0;
    for p in &graph.patches {
        *corner_hist.entry(p.corners.len()).or_default() += 1;
        if !p.is_disk() || p.concave > 0 {
            bad += 1;
        }
    }
    eprintln!(
        "graph: {} -> {} triangles, {} crossings, {} pruned, {} arcs, {} patches, corners {corner_hist:?}, {bad} not fillable, {:.2}s",
        m.f.len(), fill_mesh.f.len(), crossings, graph.pruned, graph.arcs.len(), graph.patches.len(), t_graph
    );

    if let Some(path) = args.flag("--layout") {
        write_layout(path, &fill_mesh, &graph, &s, &field.z, &sings, &sharp, &traces)?;
    }
    if std::env::var("QREMESH_DEBUG").is_ok() {
        for (i, p) in graph.patches.iter().enumerate() {
            let sides: Vec<String> = p.sides.iter().map(|side| {
                side.iter().map(|&(a, _)| format!("{:.2}", graph.arcs[a].length / quad)).collect::<Vec<_>>().join("+")
            }).collect();
            let at: Vec<String> = p.corners.iter().map(|&c| { let q = fill_mesh.v[p.verts[p.outline[c] as usize] as usize]; format!("({:.2},{:.2},{:.2})", q.x, q.y, q.z) }).collect();
            eprintln!("  patch {i}: {} corners, loops {}, euler {}, concave {}, sides [{}] at {}", p.corners.len(), p.loops, p.euler, p.concave, sides.join(", "), at.join(" "));
        }
    }

    // Quads.
    let t = Instant::now();
    let mut graph = graph;
    let mut filler = fill::Filler::new(&fill_mesh, &mut graph, quad);
    let q = if legacy { filler.build() } else { filler.build_patches() };
    let mut output = filler.place(&q.x);
    output.quantize_violations = q.violated;
    let t_fill = t.elapsed().as_secs_f64();
    eprintln!("fill: {} kites, {} arcs, {} quantize violations, {} unfilled patches, {} vertices, {} faces, {:.2}s", output.kites, output.arcs, q.violated, output.unfilled, output.v.len(), output.faces.len(), t_fill);
    let t = Instant::now();
    let projector = proj::Projector::new(&m, edge * 2.0);
    fill::smooth(&mut output, &projector, args.num("--smooth", 60)?);
    let t_smooth = t.elapsed().as_secs_f64();
    mesh::write_obj(out, &output.v, &output.faces)?;
    let metrics = metrics(&output, &m, &projector, quad);
    eprintln!("quads: {metrics}");

    println!(
        "{{\"input\": {{\"vertices\": {}, \"triangles\": {}}}, \"field\": \"{}\", \"sharp_edges\": {}, \"field_singularities\": {{\"plus\": {plus}, \"minus\": {minus}}}, \"traces\": {}, \"patches\": {}, \"patch_corners\": {corner_hist:?}, \"unfillable_patches\": {bad}, \"kites\": {}, \"quantize_violations\": {}, \"output\": {metrics}, \"seconds\": {{\"field\": {t_field:.2}, \"trace\": {t_trace:.2}, \"graph\": {t_graph:.2}, \"fill\": {t_fill:.2}, \"smooth\": {t_smooth:.2}, \"total\": {:.2}}}}}",
        m.v.len(), m.f.len(), field.how, sharp.len(), n_traces, graph.patches.len(), output.kites, output.quantize_violations, clock.elapsed().as_secs_f64()
    );
    Ok(())
}

/// The picture's data for `tools/render_layout.py`: the refined mesh (so
/// the regions are exact), the patch of each triangle, which patches can
/// be filled, traces, singularities, features, a sample of the field.
fn write_layout(path: &str, rm: &mesh::TriMesh, graph: &patches::Graph, s: &cross::Surface, z: &[cplx::C], sings: &[cross::Singularity], sharp: &[(u32, u32)], traces: &[(Vec<V3>, &str)]) -> Result<(), String> {
    let obj = format!("{path}.obj");
    let faces: Vec<Vec<u32>> = rm.f.iter().map(|t| t.to_vec()).collect();
    mesh::write_obj(&obj, &rm.v, &faces)?;
    let mut json = String::new();
    json.push_str("{\"region\": [");
    json.push_str(&graph.region.iter().map(|r| r.to_string()).collect::<Vec<_>>().join(","));
    json.push_str("], \"patch_ok\": [");
    json.push_str(&graph.patches.iter().map(|p| if p.is_disk() && p.concave == 0 && (2..=5).contains(&p.corners.len()) { "true" } else { "false" }).collect::<Vec<_>>().join(","));
    json.push_str("], \"traces\": [");
    let pts = |ps: &[V3]| ps.iter().map(|p| format!("[{:.5},{:.5},{:.5}]", p.x, p.y, p.z)).collect::<Vec<_>>().join(",");
    // QREMESH_CANDIDATES draws every candidate instead of the layout's traces.
    json.push_str(&traces.iter().map(|t| format!("[{}]", pts(&t.0))).collect::<Vec<_>>().join(","));
    json.push_str("], \"trace_kinds\": [");
    json.push_str(&traces.iter().map(|t| format!("\"{}\"", t.1)).collect::<Vec<_>>().join(","));
    json.push_str("], \"singularities\": [");
    json.push_str(&sings.iter().map(|x| format!("[{:.5},{:.5},{:.5},{}]", x.at.x, x.at.y, x.at.z, x.index)).collect::<Vec<_>>().join(","));
    json.push_str("], \"features\": [");
    json.push_str(&sharp.iter().map(|&(a, b)| format!("[{}]", pts(&[s.p[a as usize], s.p[b as usize]]))).collect::<Vec<_>>().join(","));
    json.push_str("], \"arms\": [");
    let stride = (s.p.len() / 1500).max(1);
    json.push_str(&(0..s.p.len()).step_by(stride).map(|i| {
        let a = s.arm(i, z[i]);
        format!("[{}]", pts(&[s.p[i], a, s.n[i].cross(a)]))
    }).collect::<Vec<_>>().join(","));
    json.push_str("]}");
    std::fs::write(path, json).map_err(|e| format!("{path}: {e}"))
}

/// What the result is like: how many faces are quads, the valences, how
/// even the edges are against the wanted quad side `h`, and how far the
/// result sits from the input (both ways, as a share of the bounding
/// diagonal).
fn metrics(out: &fill::Output, input: &mesh::TriMesh, proj: &proj::Projector, h: f64) -> String {
    use std::collections::{BTreeMap, HashMap};
    let mut by_size: BTreeMap<usize, usize> = BTreeMap::new();
    let mut edges: HashMap<(u32, u32), usize> = HashMap::new();
    for f in &out.faces {
        *by_size.entry(f.len()).or_default() += 1;
        for k in 0..f.len() {
            let (a, b) = (f[k], f[(k + 1) % f.len()]);
            *edges.entry((a.min(b), a.max(b))).or_default() += 1;
        }
    }
    let mut valence = vec![0usize; out.v.len()];
    let mut on_boundary = vec![false; out.v.len()];
    let mut lengths = Vec::new();
    for (&(a, b), &count) in &edges {
        valence[a as usize] += 1;
        valence[b as usize] += 1;
        if count != 2 {
            on_boundary[a as usize] = true;
            on_boundary[b as usize] = true;
        }
        lengths.push((out.v[a as usize] - out.v[b as usize]).norm() / h);
    }
    let mut hist: BTreeMap<usize, usize> = BTreeMap::new();
    let mut singular = 0;
    for i in 0..out.v.len() {
        if valence[i] == 0 {
            continue;
        }
        *hist.entry(valence[i]).or_default() += 1;
        if valence[i] != 4 && !on_boundary[i] {
            singular += 1;
        }
    }
    let open = edges.values().filter(|&&c| c != 2).count();
    let mut input_edges: HashMap<(u32, u32), usize> = HashMap::new();
    for t in &input.f {
        for k in 0..3 {
            let (a, b) = (t[k], t[(k + 1) % 3]);
            *input_edges.entry((a.min(b), a.max(b))).or_default() += 1;
        }
    }
    let input_boundary = input_edges.values().filter(|&&c| c == 1).count();
    let mean = lengths.iter().sum::<f64>() / lengths.len().max(1) as f64;
    let std = (lengths.iter().map(|l| (l - mean) * (l - mean)).sum::<f64>() / lengths.len().max(1) as f64).sqrt();
    let (lo, hi) = lengths.iter().fold((f64::MAX, f64::MIN), |a, &l| (a.0.min(l), a.1.max(l)));
    let diag = {
        let lo = input.v.iter().fold(input.v[0], |a, p| math::v3(a.x.min(p.x), a.y.min(p.y), a.z.min(p.z)));
        let hi = input.v.iter().fold(input.v[0], |a, p| math::v3(a.x.max(p.x), a.y.max(p.y), a.z.max(p.z)));
        (hi - lo).norm()
    };
    // Output vertices to the input surface.
    let d_out: Vec<f64> = out.v.iter().enumerate().filter(|(i, _)| valence[*i] > 0).map(|(_, &p)| proj.closest(p).1 / diag).collect();
    // Input vertices to the output surface, through its triangulated quads.
    let mut tris = Vec::new();
    for f in &out.faces {
        for k in 1..f.len() - 1 {
            tris.push([f[0], f[k], f[k + 1]]);
        }
    }
    let back = mesh::TriMesh { v: out.v.clone(), f: tris };
    let d_in: Vec<f64> = if back.f.is_empty() {
        Vec::new()
    } else {
        let bp = proj::Projector::new(&back, h);
        input.v.iter().step_by((input.v.len() / 4000).max(1)).map(|&p| bp.closest(p).1 / diag).collect()
    };
    let stats = |d: &[f64]| -> String {
        let mean = d.iter().sum::<f64>() / d.len().max(1) as f64;
        let max = d.iter().cloned().fold(0.0, f64::max);
        format!("{{\"mean\": {mean:.5}, \"max\": {max:.5}}}")
    };
    let faces = out.faces.len();
    format!(
        "{{\"vertices\": {}, \"faces\": {faces}, \"quads\": {}, \"quad_ratio\": {:.4}, \"faces_by_size\": {by_size:?}, \"valence\": {hist:?}, \"singular_vertices\": {singular}, \"boundary_edges\": {open}, \"input_boundary_edges\": {input_boundary}, \"edge_length_over_h\": {{\"mean\": {mean:.3}, \"std\": {std:.3}, \"min\": {lo:.3}, \"max\": {hi:.3}}}, \"distance_to_input\": {}, \"distance_from_input\": {}}}",
        valence.iter().filter(|&&v| v > 0).count(), by_size.get(&4).copied().unwrap_or(0), by_size.get(&4).copied().unwrap_or(0) as f64 / faces.max(1) as f64, stats(&d_out), stats(&d_in)
    )
}

fn premesh_only(args: &Args) -> Result<(), String> {
    let input = args.words.get(1).ok_or("premesh needs an input OBJ")?;
    let out = args.flag("-o").ok_or("premesh needs -o OUT")?;
    let m = mesh::read_obj(input)?;
    let edge: f64 = args.num("--edge", mesh::mean_edge(&m))?;
    let t = Instant::now();
    let (pm, r) = premesh::remesh(&m, edge, args.num("--features", 35.0)?, args.num("--rounds", 6)?);
    let faces: Vec<Vec<u32>> = pm.f.iter().map(|t| t.to_vec()).collect();
    mesh::write_obj(out, &pm.v, &faces)?;
    eprintln!(
        "{} -> {} triangles, slivers {:.1}% -> {:.1}%, {} feature edges, {:.2}s",
        m.f.len(), r.triangles, r.slivers_before * 100.0, r.slivers_after * 100.0, r.feature_edges, t.elapsed().as_secs_f64()
    );
    let _ = r.vertices;
    Ok(())
}

//! qremesh — Continuity's quad remesher.
//!
//!     qremesh sphere -o sphere.obj [--rings 160 --segments 320 --jitter 0.3 --seed 1]
//!     qremesh remesh in.obj -o out.obj [--faces 2000 --iterations 30 --seed 1]
//!     qremesh shape ico|cube|torus -o shape.obj [--jitter 0.3]
//!     qremesh layout in.obj -o layout.json [--align 1 --features 35 --quads 600]
//!
//! `remesh` is the first prototype (Instant Meshes' local fields). `layout`
//! is the second: a global cross field, its singularities, separatrices
//! traced into a patch layout — the front half of a QuadWild-style remesher.
//!
//! `remesh` prints a JSON report on stdout; progress goes to stderr. This is
//! the feasibility prototype: the pipeline end to end, measured, without the
//! repairs a production extraction needs.

mod cplx;
mod cross;
mod extract;
mod field;
mod math;
mod mesh;
mod shapes;
mod trace;

use math::{Rng, V3};
use std::collections::HashMap;
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
        Some("sphere") => sphere(&Args { words }),
        Some("remesh") => remesh(&Args { words }),
        Some("shape") => shape(&Args { words }),
        Some("layout") => layout(&Args { words }),
        _ => Err("usage: qremesh sphere -o OUT | qremesh remesh IN -o OUT [--faces N]".into()),
    };
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(message) => {
            eprintln!("error: {message}");
            ExitCode::FAILURE
        }
    }
}

fn sphere(args: &Args) -> Result<(), String> {
    let out = args.flag("-o").ok_or("sphere needs -o OUT")?;
    let m = mesh::uv_sphere(
        args.num("--rings", 160)?,
        args.num("--segments", 320)?,
        args.num("--jitter", 0.3)?,
        args.num("--seed", 1)?,
    );
    let faces: Vec<Vec<u32>> = m.f.iter().map(|t| t.to_vec()).collect();
    mesh::write_obj(out, &m.v, &faces)?;
    eprintln!("{} vertices, {} triangles -> {out}", m.v.len(), m.f.len());
    Ok(())
}

fn remesh(args: &Args) -> Result<(), String> {
    let input = args.words.get(1).ok_or("remesh needs an input OBJ")?;
    let out = args.flag("-o").ok_or("remesh needs -o OUT")?;
    let target: f64 = args.num("--faces", 2000.0)?;
    let iterations: usize = args.num("--iterations", 30)?;
    let seed: u64 = args.num("--seed", 1)?;
    let mut rng = Rng::new(seed);

    let clock = Instant::now();
    let m = mesh::read_obj(input)?;
    let (n, area) = mesh::normals_areas(&m);
    let adj = mesh::adjacency(m.v.len(), &m.f);
    // A quad of side h covers h²; `target` of them cover the surface.
    let h = (mesh::surface_area(&m) / target).sqrt();
    let edge = mesh::mean_edge(&m);
    eprintln!("{} vertices, {} triangles, edge {edge:.4}, quad side {h:.4}", m.v.len(), m.f.len());

    let t = Instant::now();
    let levels = field::hierarchy(m.v.clone(), n.clone(), area, adj.clone(), edge * 2.0, 64);
    let t_hierarchy = t.elapsed().as_secs_f64();
    eprintln!("hierarchy: {} levels, coarsest {} vertices", levels.len(), levels.last().unwrap().p.len());

    let t = Instant::now();
    let q = field::solve_orientation(&levels, iterations, &mut rng);
    let t_orientation = t.elapsed().as_secs_f64();
    let singular = orientation_singularities(&m, &n, &q[0]);
    eprintln!("orientation: {singular} singular triangles");

    let t = Instant::now();
    let o = field::solve_position(&levels, &q, h, iterations, &mut rng);
    let t_position = t.elapsed().as_secs_f64();

    if std::env::var("QREMESH_DEBUG").is_ok() {
        let mut bins = [0usize; 6];
        for i in 0..m.v.len() {
            for &j in &adj[i] {
                let j = j as usize;
                if j <= i { continue; }
                let qj = field::compat_orientation(q[0][i], n[i], q[0][j], n[j]).1;
                let (a, b) = field::compat_position(m.v[i], n[i], q[0][i], o[i], m.v[j], n[j], qj, o[j], h);
                let r = (a - b).norm() / h;
                bins[((r / 0.1) as usize).min(5)] += 1;
            }
        }
        eprintln!("position residual |ours-theirs|/h in 0.1 bins: {bins:?}");
        // Lattice steps around each triangle, in the first corner's frame.
        let step = |i: usize, j: usize| -> (i64, i64) {
            let ti = n[i].cross(q[0][i]);
            let qj = field::compat_orientation(q[0][i], n[i], q[0][j], n[j]).1;
            let tj = n[j].cross(qj);
            let (a, b) = field::compat_position(m.v[i], n[i], q[0][i], o[i], m.v[j], n[j], qj, o[j], h);
            let si = ((a - o[i]).dot(q[0][i]) / h, (a - o[i]).dot(ti) / h);
            let sj = ((b - o[j]).dot(qj) / h, (b - o[j]).dot(tj) / h);
            ((si.0.round() - sj.0.round()) as i64, (si.1.round() - sj.1.round()) as i64)
        };
        let turn = |(a, b): (i64, i64), r: i32| { let (mut a, mut b) = (a, b); for _ in 0..r { (a, b) = (-b, a); } (a, b) };
        let (mut sym, mut asym) = (0, 0);
        for i in 0..m.v.len() { for &j in &adj[i] { let j = j as usize; if j <= i { continue; }
            let r = field::rotation_index(q[0][i], n[i], q[0][j]);
            let a = step(i, j); let b = turn(step(j, i), r);
            if (a.0 + b.0, a.1 + b.1) == (0, 0) { sym += 1 } else { asym += 1; if asym < 4 { eprintln!("  i->j {a:?}  j->i in i frame {b:?}  r={r}"); } } } }
        eprintln!("antisymmetric steps: {sym}, not: {asym}");
        let mut singular = 0;
        for t in &m.f {
            let [i, j, k] = t.map(|x| x as usize);
            let rj = field::rotation_index(q[0][i], n[i], q[0][j]);
            let rk = field::rotation_index(q[0][i], n[i], q[0][k]);
            let s1 = step(i, j);
            let s2 = turn(step(j, k), rj);
            let s3 = turn(step(k, i), rk);
            if (s1.0 + s2.0 + s3.0, s1.1 + s2.1 + s3.1) != (0, 0) { singular += 1; }
        }
        eprintln!("position singular triangles: {singular}");
    }
    let t = Instant::now();
    let polys = extract::extract(&m.v, &n, &adj, &q[0], &o, h);
    let t_extract = t.elapsed().as_secs_f64();
    mesh::write_obj(out, &polys.v, &polys.faces)?;

    println!("{}", report(&polys, h, singular, [t_hierarchy, t_orientation, t_position, t_extract], clock.elapsed().as_secs_f64()));
    Ok(())
}

/// Input triangles around which the orientation field turns by a quarter
/// (or three): the field's singularities. A sphere needs exactly eight.
fn orientation_singularities(m: &mesh::TriMesh, n: &[V3], q: &[V3]) -> usize {
    m.f.iter()
        .filter(|t| {
            let [a, b, c] = t.map(|i| i as usize);
            let turn = field::rotation_index(q[a], n[a], q[b])
                + field::rotation_index(q[b], n[b], q[c])
                + field::rotation_index(q[c], n[c], q[a]);
            turn % 4 != 0
        })
        .count()
}

fn report(polys: &extract::Polygons, h: f64, singular: usize, stage: [f64; 4], total: f64) -> String {
    let mut by_size = [0usize; 7];
    let mut valence: HashMap<u32, usize> = HashMap::new();
    let mut edge_faces: HashMap<(u32, u32), usize> = HashMap::new();
    let mut used = vec![false; polys.v.len()];
    let mut lengths = Vec::new();
    for face in &polys.faces {
        by_size[face.len().min(6)] += 1;
        for k in 0..face.len() {
            let (a, b) = (face[k], face[(k + 1) % face.len()]);
            used[a as usize] = true;
            *edge_faces.entry((a.min(b), a.max(b))).or_default() += 1;
        }
    }
    for (&(a, b), _) in &edge_faces {
        *valence.entry(a).or_default() += 1;
        *valence.entry(b).or_default() += 1;
        lengths.push((polys.v[a as usize] - polys.v[b as usize]).norm() / h);
    }
    let vertices = used.iter().filter(|&&u| u).count();
    let edges = edge_faces.len();
    let faces = polys.faces.len();
    let not_two = edge_faces.values().filter(|&&c| c != 2).count();
    let mut histogram = [0usize; 9];
    for (_, &d) in &valence {
        histogram[d.min(8)] += 1;
    }
    let irregular: usize = valence.values().filter(|&&d| d != 4).count();
    let mean = lengths.iter().sum::<f64>() / lengths.len().max(1) as f64;
    let spread = (lengths.iter().map(|l| (l - mean) * (l - mean)).sum::<f64>()
        / lengths.len().max(1) as f64)
        .sqrt();
    let radius: Vec<f64> = polys.v.iter().zip(&used).filter(|(_, &u)| u).map(|(p, _)| p.norm()).collect();
    let r_mean = radius.iter().sum::<f64>() / radius.len().max(1) as f64;
    let r_dev = radius.iter().map(|r| (r - 1.0).abs()).fold(0.0, f64::max);
    format!(
        concat!(
            "{{\"vertices\": {}, \"edges\": {}, \"faces\": {}, ",
            "\"quads\": {}, \"triangles\": {}, \"pentagons\": {}, \"hexagons\": {}, ",
            "\"quad_ratio\": {:.4}, \"euler\": {}, \"edges_not_shared_by_two\": {}, ",
            "\"open_cycles\": {}, \"irregular_vertices\": {}, \"valence\": {:?}, ",
            "\"orientation_singular_triangles\": {}, ",
            "\"edge_length_over_h\": {{\"mean\": {:.3}, \"std\": {:.3}}}, ",
            "\"radius\": {{\"mean\": {:.4}, \"max_off_unit\": {:.4}}}, ",
            "\"seconds\": {{\"hierarchy\": {:.2}, \"orientation\": {:.2}, \"position\": {:.2}, \"extract\": {:.2}, \"total\": {:.2}}}}}"
        ),
        vertices, edges, faces,
        by_size[4], by_size[3], by_size[5], by_size[6],
        by_size[4] as f64 / faces.max(1) as f64,
        vertices as i64 - edges as i64 + faces as i64,
        not_two, polys.open_cycles, irregular, histogram,
        singular, mean, spread, r_mean, r_dev,
        stage[0], stage[1], stage[2], stage[3], total,
    )
}

fn shape(args: &Args) -> Result<(), String> {
    let out = args.flag("-o").ok_or("shape needs -o OUT")?;
    let mut m = match args.words.get(1).map(String::as_str) {
        Some("ico") => shapes::icosphere(args.num("--subdivisions", 5)?),
        Some("cube") => shapes::cube(args.num("--n", 40)?),
        Some("torus") => shapes::torus(1.0, 0.4, args.num("--nu", 160)?, args.num("--nv", 64)?),
        _ => return Err("shape: ico, cube or torus".into()),
    };
    let jitter: f64 = args.num("--jitter", 0.3)?;
    if jitter > 0.0 {
        shapes::jitter(&mut m, jitter, args.num("--seed", 1)?);
    }
    let faces: Vec<Vec<u32>> = m.f.iter().map(|t| t.to_vec()).collect();
    mesh::write_obj(out, &m.v, &faces)?;
    eprintln!("{} vertices, {} triangles -> {out}", m.v.len(), m.f.len());
    Ok(())
}

fn layout(args: &Args) -> Result<(), String> {
    let input = args.words.get(1).ok_or("layout needs an input OBJ")?;
    let out = args.flag("-o").ok_or("layout needs -o OUT")?;
    let align: f64 = args.num("--align", 0.05)?;
    let degrees: f64 = args.num("--features", 35.0)?;
    let mut rng = Rng::new(args.num("--seed", 1)?);

    let clock = Instant::now();
    let m = mesh::read_obj(input)?;
    let s = cross::Surface::new(&m);
    let target = cross::curvature_target(&s);
    let (fixed, sharp) = cross::feature_constraints(&s, degrees);
    let t = Instant::now();
    let field = cross::solve(&s, &target, &fixed, align, &mut rng);
    let t_field = t.elapsed().as_secs_f64();
    let sings = cross::singularities(&s, &field.z);
    let plus = sings.iter().filter(|x| x.index > 0).count();
    let minus = sings.len() - plus;
    eprintln!("field ({}): {} solver iterations, {:.2}s; singularities +{plus} -{minus}", field.how, field.solver_iterations, t_field);

    let edge = mesh::mean_edge(&m);
    let diameter = {
        let lo = m.v.iter().fold(V3::ZERO, |a, p| math::v3(a.x.min(p.x), a.y.min(p.y), a.z.min(p.z)));
        let hi = m.v.iter().fold(V3::ZERO, |a, p| math::v3(a.x.max(p.x), a.y.max(p.y), a.z.max(p.z)));
        (hi - lo).norm()
    };
    let t = Instant::now();
    let lay = trace::layout(&s, &field.z, &sings, &sharp, edge * 0.5, diameter * 3.0);
    let t_trace = t.elapsed().as_secs_f64();
    let mut ended: std::collections::BTreeMap<&str, usize> = Default::default();
    for tr in &lay.traces {
        *ended.entry(tr.ended).or_default() += 1;
    }
    let mut seps: std::collections::BTreeMap<usize, usize> = Default::default();
    for k in 0..sings.len() {
        *seps.entry(lay.traces.iter().filter(|t| t.from == k).count()).or_default() += 1;
    }

    // The picture's data: regions, traces, singularities, features.
    let mut json = String::new();
    json.push_str("{\"region\": [");
    json.push_str(&lay.region.iter().map(|r| r.to_string()).collect::<Vec<_>>().join(","));
    json.push_str("], \"traces\": [");
    let pts = |ps: &[V3]| ps.iter().map(|p| format!("[{:.5},{:.5},{:.5}]", p.x, p.y, p.z)).collect::<Vec<_>>().join(",");
    json.push_str(&lay.traces.iter().map(|t| format!("[{}]", pts(&t.points))).collect::<Vec<_>>().join(","));
    json.push_str("], \"singularities\": [");
    json.push_str(&sings.iter().map(|x| format!("[{:.5},{:.5},{:.5},{}]", x.at.x, x.at.y, x.at.z, x.index)).collect::<Vec<_>>().join(","));
    json.push_str("], \"features\": [");
    json.push_str(&sharp.iter().map(|&(a, b)| format!("[{}]", pts(&[m.v[a as usize], m.v[b as usize]]))).collect::<Vec<_>>().join(","));
    json.push_str("], \"arms\": [");
    let stride = (m.v.len() / 1500).max(1);
    json.push_str(&(0..m.v.len()).step_by(stride).map(|i| {
        let a = s.arm(i, field.z[i]);
        format!("[{}]", pts(&[m.v[i], a, s.n[i].cross(a)]))
    }).collect::<Vec<_>>().join(","));
    json.push_str("]}");
    std::fs::write(out, json).map_err(|e| format!("{out}: {e}"))?;

    let big: Vec<i64> = {
        let mut sizes = vec![0i64; lay.regions];
        for &r in &lay.region { sizes[r as usize] += 1; }
        let mut v: Vec<i64> = (0..lay.regions).filter(|&r| lay.region_euler[r] != 1).map(|r| lay.region_euler[r]).collect();
        v.sort();
        v
    };
    // Patches: regions holding more than half a percent of the surface. The
    // rest are slivers where traces meet inside one triangle.
    let patches = {
        let mut sizes = vec![0usize; lay.regions];
        for &r in &lay.region { sizes[r as usize] += 1; }
        sizes.iter().filter(|&&n| n * 200 > m.f.len()).count()
    };
    eprintln!("patches (>0.5% of the surface): {patches}");
    println!(
        "{{\"vertices\": {}, \"triangles\": {}, \"field\": \"{}\", \"solver_iterations\": {}, \"sharp_edges\": {}, \"fixed_vertices\": {}, \"singularities\": {{\"plus\": {plus}, \"minus\": {minus}}}, \"separatrices_per_singularity\": {seps:?}, \"traces\": {}, \"trace_ends\": {ended:?}, \"regions\": {}, \"disks\": {}, \"non_disk_euler\": {big:?}, \"repairs\": {}, \"seconds\": {{\"field\": {t_field:.2}, \"trace\": {t_trace:.2}, \"total\": {:.2}}}}}",
        m.v.len(), m.f.len(), field.how, field.solver_iterations, sharp.len(),
        fixed.iter().filter(|f| f.is_some()).count(),
        lay.traces.len(), lay.regions, lay.disks, lay.repairs, clock.elapsed().as_secs_f64()
    );
    Ok(())
}

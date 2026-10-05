//! qremesh — Continuity's quad remesher.
//!
//!     qremesh sphere -o sphere.obj [--rings 160 --segments 320 --jitter 0.3 --seed 1]
//!     qremesh remesh in.obj -o out.obj [--faces 2000 --iterations 30 --seed 1]
//!
//! `remesh` prints a JSON report on stdout; progress goes to stderr. This is
//! the feasibility prototype: the pipeline end to end, measured, without the
//! repairs a production extraction needs.

mod extract;
mod field;
mod math;
mod mesh;

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

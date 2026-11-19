use std::collections::HashMap;

use numpy::{ndarray::ArrayView3, PyReadonlyArray2, PyReadonlyArray3, PyReadwriteArray1};
use pyo3::{exceptions::PyValueError, prelude::*};

type Index = [usize; 3];
const CORNERS: [Index; 8] = [
    [0, 0, 0],
    [0, 0, 1],
    [0, 1, 0],
    [0, 1, 1],
    [1, 0, 0],
    [1, 0, 1],
    [1, 1, 0],
    [1, 1, 1],
];

struct Stencil {
    member: usize,
    neighbours: [Index; 2],
    weights: [[f64; 3]; 2],
}

impl Stencil {
    fn corner(&self, side: Index) -> (Index, f64) {
        let [z, y, x] = side;
        let index = [
            self.neighbours[z][0],
            self.neighbours[y][1],
            self.neighbours[x][2],
        ];
        let weight = self.weights[z][0] * self.weights[y][1] * self.weights[x][2];
        (index, weight)
    }
}

#[derive(Default)]
struct ChunkSamples {
    inside: Vec<Stencil>,
    crossing: Vec<(usize, Index, f64)>,
}

#[pyclass]
struct SamplingPlan {
    shape: Index,
    chunks: Index,
    samples: usize,
    groups: HashMap<Index, ChunkSamples>,
}

impl SamplingPlan {
    fn add(&mut self, member: usize, coords: [f64; 3]) {
        let clamped: [f64; 3] =
            std::array::from_fn(|axis| coords[axis].clamp(0.0, (self.shape[axis] - 1) as f64));
        let base = clamped.map(|coordinate| coordinate as usize);
        let next = std::array::from_fn(|axis| (base[axis] + 1).min(self.shape[axis] - 1));
        let fraction: [f64; 3] = std::array::from_fn(|axis| clamped[axis] - base[axis] as f64);
        let mut stencil = Stencil {
            member,
            neighbours: [base, next],
            weights: [fraction.map(|value| 1.0 - value), fraction],
        };
        let lower_key: Index = std::array::from_fn(|axis| base[axis] / self.chunks[axis]);
        let upper_key: Index = std::array::from_fn(|axis| next[axis] / self.chunks[axis]);
        if lower_key == upper_key {
            stencil.neighbours = [base, next].map(|index| {
                std::array::from_fn(|axis| index[axis] - lower_key[axis] * self.chunks[axis])
            });
            self.groups
                .entry(lower_key)
                .or_default()
                .inside
                .push(stencil);
            return;
        }
        for side in CORNERS {
            let (index, weight) = stencil.corner(side);
            let key = std::array::from_fn(|axis| [lower_key, upper_key][side[axis]][axis]);
            let local = std::array::from_fn(|axis| index[axis] - key[axis] * self.chunks[axis]);
            self.groups
                .entry(key)
                .or_default()
                .crossing
                .push((member, local, weight));
        }
    }

    fn accumulate<T: Copy + Into<f64>>(
        &self,
        key: Index,
        block: ArrayView3<'_, T>,
        out: &mut [f64],
    ) -> PyResult<()> {
        let group = self
            .groups
            .get(&key)
            .ok_or_else(|| PyValueError::new_err("Unknown chunk"))?;
        let expected: Index = std::array::from_fn(|axis| {
            self.chunks[axis].min(self.shape[axis] - key[axis] * self.chunks[axis])
        });
        if block.shape() != expected || out.len() != self.samples {
            return Err(PyValueError::new_err("Unexpected block or output shape"));
        }
        for stencil in &group.inside {
            let mut value = 0.0;
            for side in CORNERS {
                let (index, weight) = stencil.corner(side);
                value += weight * block[index].into();
            }
            out[stencil.member] += value;
        }
        for &(member, index, weight) in &group.crossing {
            out[member] += weight * block[index].into();
        }
        Ok(())
    }
}

#[pymethods]
impl SamplingPlan {
    fn keys(&self) -> Vec<Index> {
        let mut keys: Vec<_> = self.groups.keys().copied().collect();
        keys.sort_unstable();
        keys
    }

    fn add_u8(
        &self,
        key: Index,
        block: PyReadonlyArray3<'_, u8>,
        mut out: PyReadwriteArray1<'_, f64>,
    ) -> PyResult<()> {
        self.accumulate(key, block.as_array(), out.as_slice_mut()?)
    }

    fn add_u16(
        &self,
        key: Index,
        block: PyReadonlyArray3<'_, u16>,
        mut out: PyReadwriteArray1<'_, f64>,
    ) -> PyResult<()> {
        self.accumulate(key, block.as_array(), out.as_slice_mut()?)
    }
}

#[pyfunction]
fn plan(
    coords: PyReadonlyArray2<'_, f64>,
    shape: Index,
    chunks: Index,
) -> PyResult<Option<SamplingPlan>> {
    let coords = coords.as_array();
    if coords.ncols() != 3
        || shape.contains(&0)
        || chunks.contains(&0)
        || shape.iter().any(|&n| n as u64 >= (1_u64 << 53))
    {
        return Err(PyValueError::new_err(
            "Expected (N, 3) coordinates and positive dimensions",
        ));
    }
    let mut plan = SamplingPlan {
        shape,
        chunks,
        samples: coords.nrows(),
        groups: HashMap::new(),
    };
    for (member, row) in coords.rows().into_iter().enumerate() {
        let coords = [row[0], row[1], row[2]];
        if !coords.iter().all(|coordinate| coordinate.is_finite()) {
            return Ok(None);
        }
        plan.add(member, coords);
    }
    Ok(Some(plan))
}

#[pymodule(gil_used = true)]
fn vesuvius_explorer_rust(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(plan, module)?)
}

#[cfg(test)]
mod tests {
    use super::*;
    use numpy::ndarray::Array3;

    #[test]
    fn samples_across_eight_chunks_and_clamps_on_partial_edges() {
        let mut plan = SamplingPlan {
            shape: [3, 4, 5],
            chunks: [2, 2, 2],
            samples: 3,
            groups: HashMap::new(),
        };
        plan.add(0, [1.5, 1.5, 1.5]);
        plan.add(1, [-120.0, 30.0, 30.0]);
        plan.add(2, [0.25, 0.25, 0.25]);
        let mut result = [0.0; 3];
        for key in plan.keys() {
            let origin: Index = key.map(|axis| axis * 2);
            let shape: Index = std::array::from_fn(|i| (plan.shape[i] - origin[i]).min(2));
            let block = Array3::from_shape_fn(shape, |(z, y, x)| {
                ((z + origin[0]) * 100 + (y + origin[1]) * 10 + x + origin[2]) as u16
            });
            plan.accumulate(key, block.view(), &mut result).unwrap();
        }
        assert_eq!(result, [166.5, 34.0, 27.75]);
    }

    #[test]
    fn samples_strided_blocks_and_singleton_axes() {
        use numpy::ndarray::s;

        let mut plan = SamplingPlan {
            shape: [1, 2, 2],
            chunks: [1, 2, 2],
            samples: 2,
            groups: HashMap::new(),
        };
        plan.add(0, [99.0, 0.5, 0.5]);
        plan.add(1, [0.0, 1.0, 0.0]);
        let volume =
            Array3::<u8>::from_shape_vec((1, 2, 4), vec![5, 0, 9, 0, 15, 0, 19, 0]).unwrap();
        let mut result = [0.0; 2];
        plan.accumulate([0, 0, 0], volume.slice(s![.., .., ..;2]), &mut result)
            .unwrap();
        assert_eq!(result, [12.0, 15.0]);
    }
}

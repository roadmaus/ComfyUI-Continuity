//! Complex numbers, just enough for cross fields.
//!
//! A cross — four directions a quarter turn apart — is stored as one complex
//! number: the angle of any of its four arms, times four, as the argument.
//! All four arms give the same number, which is what makes the field
//! smoothable by ordinary linear algebra.

use std::ops::{Add, AddAssign, Mul, Sub, SubAssign};

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct C {
    pub re: f64,
    pub im: f64,
}

impl C {
    pub const ZERO: C = C { re: 0.0, im: 0.0 };

    pub fn polar(r: f64, angle: f64) -> C {
        C { re: r * angle.cos(), im: r * angle.sin() }
    }

    pub fn conj(self) -> C {
        C { re: self.re, im: -self.im }
    }

    pub fn abs2(self) -> f64 {
        self.re * self.re + self.im * self.im
    }

    pub fn abs(self) -> f64 {
        self.abs2().sqrt()
    }

    pub fn arg(self) -> f64 {
        self.im.atan2(self.re)
    }

    pub fn scale(self, s: f64) -> C {
        C { re: self.re * s, im: self.im * s }
    }
}

impl Add for C {
    type Output = C;
    fn add(self, o: C) -> C {
        C { re: self.re + o.re, im: self.im + o.im }
    }
}

impl Sub for C {
    type Output = C;
    fn sub(self, o: C) -> C {
        C { re: self.re - o.re, im: self.im - o.im }
    }
}

impl Mul for C {
    type Output = C;
    fn mul(self, o: C) -> C {
        C { re: self.re * o.re - self.im * o.im, im: self.re * o.im + self.im * o.re }
    }
}

impl AddAssign for C {
    fn add_assign(&mut self, o: C) {
        *self = *self + o;
    }
}

impl SubAssign for C {
    fn sub_assign(&mut self, o: C) {
        *self = *self - o;
    }
}

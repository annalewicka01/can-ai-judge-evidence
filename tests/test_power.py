"""Independent mathematical fixtures; not benchmark or clinical cases."""
import math
import unittest
from fractions import Fraction

from can_ai_judge_evidence.power import binomial_power


def exact_tail(n: int, p: Fraction, k: int) -> Fraction:
    return sum((Fraction(math.comb(n, j)) * p**j * (1-p)**(n-j)
                for j in range(k, n+1)), Fraction(0))


class PowerTests(unittest.TestCase):
    def test_canonical_audits(self):
        for n, k, alpha, power in (
            (500, 6, 0.04160282036792758, 0.23292864987232248),
            (3800, 27, 0.04812670283599169, 0.8033023677614939),
        ):
            with self.subTest(n=n):
                result = binomial_power(n, .005, 70/8500)
                self.assertEqual(result.k_star, k)
                self.assertAlmostEqual(result.actual_alpha, alpha, delta=1e-12)
                self.assertAlmostEqual(result.power, power, delta=1e-12)

    def test_independent_fraction_oracle(self):
        probabilities = (Fraction(0), Fraction(1, 10), Fraction(1, 4),
                         Fraction(1, 2), Fraction(3, 4), Fraction(1))
        limit = Fraction(1, 20)
        for n in range(1, 13):
            for p0 in probabilities:
                for p1 in probabilities:
                    if p1 < p0:
                        continue
                    with self.subTest(n=n, p0=p0, p1=p1):
                        k = next(k for k in range(1, n+2)
                                 if exact_tail(n, p0, k) <= limit)
                        result = binomial_power(n, float(p0), float(p1))
                        self.assertEqual(result.k_star, k)
                        self.assertAlmostEqual(result.actual_alpha,
                                               float(exact_tail(n, p0, k)), delta=1e-12)
                        self.assertAlmostEqual(result.power,
                                               float(exact_tail(n, p1, k)), delta=1e-12)
                        self.assertLessEqual(result.actual_alpha, .05)
                        if k > 1:
                            self.assertGreater(exact_tail(n, p0, k-1), limit)

    def test_equal_worlds(self):
        result = binomial_power(500, .005, .005)
        self.assertEqual(result.actual_alpha, result.power)
        self.assertLess(result.power, .05)

    def test_degenerate_worlds(self):
        for p in (0., 1.):
            result = binomial_power(20, p, p)
            self.assertEqual(result.power, 0.)
            self.assertEqual(result.actual_alpha, 0.)
            self.assertEqual(result.k_star, 1 if p == 0 else 21)
        result = binomial_power(20, 0., .1)
        self.assertEqual(result.k_star, 1)
        self.assertAlmostEqual(result.power, 1-.9**20, delta=1e-12)

    def test_discrete_power_decreases(self):
        three = binomial_power(3, .1, .2)
        four = binomial_power(4, .1, .2)
        self.assertEqual((three.k_star, four.k_star), (2, 3))
        self.assertAlmostEqual(three.power, .104, delta=1e-12)
        self.assertAlmostEqual(four.power, .0272, delta=1e-12)
        self.assertLess(four.power, three.power)

    def test_bad_inputs(self):
        for n in (0, -1, 2.5, True, '5', 2**53):
            with self.subTest(n=n), self.assertRaises(ValueError):
                binomial_power(n, .1, .2)
        for p0, p1 in ((-.1, .2), (.2, .1), (0, 1.1),
                       (float('nan'), .2), (.1, float('inf')), (True, 1)):
            with self.subTest(p0=p0, p1=p1), self.assertRaises(ValueError):
                binomial_power(5, p0, p1)
        for alpha in (0, 1, -.1, float('nan'), True):
            with self.subTest(alpha=alpha), self.assertRaises(ValueError):
                binomial_power(5, .1, .2, alpha_limit=alpha)


if __name__ == '__main__':
    unittest.main()

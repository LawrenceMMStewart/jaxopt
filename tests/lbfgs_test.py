# Copyright 2021 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from absl.testing import absltest
from absl.testing import parameterized

from jax import test_util as jtu
import jax.numpy as jnp

import numpy as onp

from jaxopt._src.lbfgs import inv_hessian_product
from jaxopt._src.lbfgs import init_history
from jaxopt._src.lbfgs import update_history

from jaxopt import LBFGS
from jaxopt import objective
from jaxopt._src import test_util


from sklearn import datasets


def materialize_inv_hessian(s_history, y_history, rho_history):
  history_size, n_dim = s_history.shape
  I = jnp.eye(n_dim, n_dim)
  H = I

  for k in range(history_size):
    V = I - rho_history[k] * jnp.outer(y_history[k], s_history[k])
    H = (jnp.dot(V.T, jnp.dot(H, V)) +
         rho_history[k] * jnp.outer(s_history[k], s_history[k]))

  return H


class LbfgsTest(jtu.JaxTestCase):

  def test_inv_hessian_product(self):
    """Test inverse Hessian product with pytrees."""

    rng = onp.random.RandomState(0)
    history_size = 4
    shape1 = (3, 2)
    shape2 = (5,)

    s_history1 = rng.randn(history_size, *shape1)
    y_history1 = rng.randn(history_size, *shape1)

    s_history2 = rng.randn(history_size, *shape2)
    y_history2 = rng.randn(history_size, *shape2)
    rho_history2 = jnp.array([1./ jnp.vdot(s_history2[i], y_history2[i])
                              for i in range(history_size)])

    v1 = rng.randn(*shape1)
    v2 = rng.randn(*shape2)
    pytree = (v1, v2)

    s_history = (s_history1, s_history2)
    y_history = (y_history1, y_history2)

    inv_rho_history = [jnp.vdot(s_history1[i], y_history1[i]) +
                       jnp.vdot(s_history2[i], y_history2[i])
                       for i in range(history_size)]
    rho_history = 1./ jnp.array(inv_rho_history)

    H1 = materialize_inv_hessian(s_history1.reshape(history_size, -1),
                                 y_history1.reshape(history_size, -1),
                                 rho_history)
    H2 = materialize_inv_hessian(s_history2, y_history2, rho_history)
    Hv1 = jnp.dot(H1, v1.reshape(-1)).reshape(shape1)
    Hv2 = jnp.dot(H2, v2)

    Hv = inv_hessian_product(pytree, s_history, y_history, rho_history)
    self.assertArraysAllClose(Hv[0], Hv1, atol=1e-2)
    self.assertArraysAllClose(Hv[1], Hv2, atol=1e-2)

  def test_init_history(self):
    # Check 1d array case.
    arr1 = jnp.zeros(5)
    history = init_history(pytree=arr1, history_size=3)
    self.assertEqual(history.shape, (3, 5))

    # Check 2d array case.
    arr2 = jnp.zeros((5, 6))
    history = init_history(pytree=arr2, history_size=3)
    self.assertEqual(history.shape, (3, 5, 6))

    # Check pytree case.
    pytree = (arr1, arr2)
    history = init_history(pytree=pytree, history_size=3)
    self.assertEqual(history[0].shape, (3, 5))
    self.assertEqual(history[1].shape, (3, 5, 6))

  def test_update_history(self):
    n_data = 4
    n_dim = 5
    history_size = 3

    # Check array case.
    rng = onp.random.RandomState(0)
    s = rng.randn(n_data, n_dim)
    s_history = init_history(s[0], history_size)

    s_history = update_history(s_history, s[0])
    self.assertArraysAllClose(s_history[-1:], s[:1])

    s_history = update_history(s_history, s[1])
    self.assertArraysAllClose(s_history[-2:], s[:2])

    s_history = update_history(s_history, s[2])
    self.assertArraysAllClose(s_history, s[:3])

    s_history = update_history(s_history, s[3])
    self.assertArraysAllClose(s_history, s[1:4])

    # Check pytree case.
    s_history_pytree = init_history((s[0], s[0]), history_size)

    s_history_pytree = update_history(s_history_pytree, (s[0], s[0]))
    self.assertArraysAllClose(s_history_pytree[0][-1:], s[:1])
    self.assertArraysAllClose(s_history_pytree[1][-1:], s[:1])

    s_history_pytree = update_history(s_history_pytree, (s[1], s[1]))
    self.assertArraysAllClose(s_history_pytree[0][-2:], s[:2])
    self.assertArraysAllClose(s_history_pytree[1][-2:], s[:2])

    s_history_pytree = update_history(s_history_pytree, (s[2], s[2]))
    self.assertArraysAllClose(s_history_pytree[0], s[:3])
    self.assertArraysAllClose(s_history_pytree[1], s[:3])

    s_history_pytree = update_history(s_history_pytree, (s[3], s[3]))
    self.assertArraysAllClose(s_history_pytree[0], s[1:4])
    self.assertArraysAllClose(s_history_pytree[1], s[1:4])

  @parameterized.product(use_gamma=[True, False])
  def test_binary_logreg(self, use_gamma):
    X, y = datasets.make_classification(n_samples=10, n_features=5,
                                        n_classes=2, n_informative=3,
                                        random_state=0)
    data = (X, y)
    fun = objective.binary_logreg

    w_init = jnp.zeros(X.shape[1])
    lbfgs = LBFGS(fun=fun, tol=1e-3, maxiter=500, use_gamma=use_gamma)
    w_fit, info = lbfgs.run(w_init, data=data)

    # Check optimality conditions.
    self.assertLessEqual(info.error, 5e-2)

    # Compare against sklearn.
    w_skl = test_util.logreg_skl(X, y, 1e-6, fit_intercept=False,
                                 multiclass=False)
    self.assertArraysAllClose(w_fit, w_skl, atol=5e-2)

  @parameterized.product(use_gamma=[True, False])
  def test_multiclass_logreg(self, use_gamma):
    X, y = datasets.make_classification(n_samples=10, n_features=5,
                                        n_classes=3, n_informative=3,
                                        random_state=0)
    data = (X, y)
    fun = objective.multiclass_logreg_with_intercept

    W_init = jnp.zeros((X.shape[1], 3))
    b_init = jnp.zeros(3)
    pytree_init = (W_init, b_init)

    lbfgs = LBFGS(fun=fun, tol=1e-3, maxiter=500, use_gamma=use_gamma)
    pytree_fit, info = lbfgs.run(pytree_init, data=data)

    # Check optimality conditions.
    self.assertLessEqual(info.error, 1e-2)


if __name__ == '__main__':
  absltest.main(testLoader=jtu.JaxTestLoader())
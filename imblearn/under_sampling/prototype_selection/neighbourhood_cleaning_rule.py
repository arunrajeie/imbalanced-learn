"""Class performing under-sampling based on the neighbourhood cleaning rule."""

# Authors: Guillaume Lemaitre <g.lemaitre58@gmail.com>
#          Christos Aridas
# License: MIT

from __future__ import division, print_function

from collections import Counter

import numpy as np
from scipy.stats import mode

from ...base import MultiClassSamplerMixin
from ..base import BaseUnderSampler
from .edited_nearest_neighbours import EditedNearestNeighbours
from ...utils import check_neighbors_object

SEL_KIND = ('all', 'mode')


class NeighbourhoodCleaningRule(BaseUnderSampler, MultiClassSamplerMixin):
    """Class performing under-sampling based on the neighbourhood cleaning
    rule.

    Parameters
    ----------
    return_indices : bool, optional (default=False)
        Whether or not to return the indices of the samples randomly
        selected from the majority class.

    random_state : int, RandomState instance or None, optional (default=None)
        If int, random_state is the seed used by the random number generator;
        If RandomState instance, random_state is the random number generator;
        If None, the random number generator is the RandomState instance used
        by np.random.

    size_ngh : int, optional (default=None)
        Size of the neighbourhood to consider to compute the average
        distance to the minority point samples.

        NOTE: size_ngh is deprecated from 0.2 and will be replaced in 0.4
        Use ``n_neighbors`` instead.

    n_neighbors : int or object, optional (default=3)
        If int, size of the neighbourhood to consider in order to make
        the comparison between each samples and their NN.
        If object, an estimator that inherits from
        `sklearn.neighbors.base.KNeighborsMixin` that will be used to find
        the k_neighbors.

    n_jobs : int, optional (default=1)
        The number of threads to open if possible.

    Attributes
    ----------
    X_shape_ : tuple of int
        Shape of the data `X` during fitting.

    ratio_ : dict
        Dictionary in which the keys are the classes which will be
        under-sampled. The values are not used.

    Notes
    -----
    Supports multi-class sampling.

    Examples
    --------

    >>> from collections import Counter
    >>> from sklearn.datasets import make_classification
    >>> from imblearn.under_sampling import \
    NeighbourhoodCleaningRule # doctest: +NORMALIZE_WHITESPACE
    >>> X, y = make_classification(n_classes=2, class_sep=2,
    ... weights=[0.1, 0.9], n_informative=3, n_redundant=1, flip_y=0,
    ... n_features=20, n_clusters_per_class=1, n_samples=1000, random_state=10)
    >>> print('Original dataset shape {}'.format(Counter(y)))
    Original dataset shape Counter({1: 900, 0: 100})
    >>> ncr = NeighbourhoodCleaningRule(random_state=42)
    >>> X_res, y_res = ncr.fit_sample(X, y)
    >>> print('Resampled dataset shape {}'.format(Counter(y_res)))
    Resampled dataset shape Counter({1: 877, 0: 100})

    References
    ----------
    .. [1] J. Laurikkala, "Improving identification of difficult small classes
       by balancing class distribution," Springer Berlin Heidelberg, 2001.

    """

    def __init__(self,
                 ratio='auto',
                 return_indices=False,
                 random_state=None,
                 size_ngh=None,
                 n_neighbors=3,
                 kind_sel='all',
                 threshold_cleaning=0.5,
                 n_jobs=1):
        super(NeighbourhoodCleaningRule, self).__init__(
            ratio=ratio, random_state=random_state)
        self.return_indices = return_indices
        self.size_ngh = size_ngh
        self.n_neighbors = n_neighbors
        self.kind_sel = kind_sel
        self.threshold_cleaning = threshold_cleaning
        self.n_jobs = n_jobs

    def fit(self, X, y):
        """Find the classes statistics before to perform sampling.

        Parameters
        ----------
        X : ndarray, shape (n_samples, n_features)
            Matrix containing the data which have to be sampled.

        y : ndarray, shape (n_samples, )
            Corresponding label for each sample in X.

        Returns
        -------
        self : object,
            Return self.

        """
        super(NeighbourhoodCleaningRule, self).fit(X, y)
        self.nn_ = check_neighbors_object('n_neighbors', self.n_neighbors,
                                          additional_neighbor=1)
        self.nn_.set_params(**{'n_jobs': self.n_jobs})

        if self.kind_sel not in SEL_KIND:
            raise NotImplementedError

        if self.threshold_cleaning > 1 or self.threshold_cleaning < 0:
            raise ValueError("'threshold_cleaning' is a value between 0 and 1."
                             " Got {} instead.".format(
                                 self.threshold_cleaning))

        return self

    def _sample(self, X, y):
        """Resample the dataset.

        Parameters
        ----------
        X : ndarray, shape (n_samples, n_features)
            Matrix containing the data which have to be sampled.

        y : ndarray, shape (n_samples, )
            Corresponding label for each sample in X.

        Returns
        -------
        X_resampled : ndarray, shape (n_samples_new, n_features)
            The array containing the resampled data.

        y_resampled : ndarray, shape (n_samples_new)
            The corresponding label of `X_resampled`

        idx_under : ndarray, shape (n_samples, )
            If `return_indices` is `True`, a boolean array will be returned
            containing the which samples have been selected.

        """
        enn = EditedNearestNeighbours(ratio=self.ratio, return_indices=True,
                                      random_state=self.random_state,
                                      size_ngh=self.size_ngh,
                                      n_neighbors=self.n_neighbors,
                                      kind_sel='mode',
                                      n_jobs=self.n_jobs)
        _, _, index_not_a1 = enn.fit_sample(X, y)
        index_a1 = np.ones(y.shape, dtype=bool)
        index_a1[index_not_a1] = False
        index_a1 = np.flatnonzero(index_a1)

        # clean the neighborhood
        target_stats = Counter(y)
        class_minority = min(target_stats, key=target_stats.get)
        # compute which classes to consider for cleaning for the A2 group
        classes_under_sample = [c for c, n_samples in target_stats.items()
                                if (c in self.ratio_.keys() and
                                    (n_samples > X.shape[0] *
                                     self.threshold_cleaning))]
        self.nn_.fit(X)
        X_class = X[y == class_minority]
        y_class = y[y == class_minority]
        nnhood_idx = self.nn_.kneighbors(
            X_class, return_distance=False)[:, 1:]
        nnhood_label = y[nnhood_idx]
        if self.kind_sel == 'mode':
            nnhood_label_majority, _ = mode(nnhood_label, axis=1)
            nnhood_bool = np.ravel(nnhood_label_majority) == y_class
        elif self.kind_sel == 'all':
            nnhood_label_majority = nnhood_label == class_minority
            nnhood_bool = np.all(nnhood_label, axis=1)
        # compute a2 group
        index_a2 = np.ravel(nnhood_idx[~nnhood_bool])
        index_a2 = np.unique([index for index in index_a2
                              if y[index] in classes_under_sample])

        union_a1_a2 = np.union1d(index_a1, index_a2).astype(int)
        selected_samples = np.ones(y.shape, dtype=bool)
        selected_samples[union_a1_a2] = False
        index_target_class = np.flatnonzero(selected_samples)

        self.logger.info('Under-sampling performed: %s', Counter(
            y[index_target_class]))

        if self.return_indices:
            return (X[index_target_class], y[index_target_class],
                    index_target_class)
        else:
            return X[index_target_class], y[index_target_class]
